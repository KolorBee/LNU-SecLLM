import base64
import json
import logging
import re
import os
from typing import Any, Dict, List

from openai import OpenAI
from backend.services.trade.trade_config import settings
from backend.shared.stock_utils import StockCodeUtil

logger = logging.getLogger(__name__)

class SimulationOCRService:
    """
    Service for recognizing stock holdings from images using Qwen-VL.
    """

    def __init__(self):
        # We assume DASHSCOPE_API_KEY is available in environment or settings
        api_key = getattr(settings, "DASHSCOPE_API_KEY", None) or os.getenv("DASHSCOPE_API_KEY")
        if not api_key:
            logger.warning("DASHSCOPE_API_KEY not found. OCR functionality will be disabled.")
            self.client = None
        else:
            self.client = OpenAI(
                api_key=api_key,
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            )
        
        self.model_name = "qwen-vl-max" # Or qwen-vl-max for better performance
        self.stock_index = self._load_stock_index()

    def _load_stock_index(self) -> Dict[str, str]:
        """加载股票索引，建立 名称 -> 代码 的映射"""
        try:
            # 尝试多个可能的路径
            # ocr_service.py is at backend/services/trade/simulation/services/ocr_service.py
            # Go up 6 levels to reach the project root
            base_dir = os.path.dirname(os.path.abspath(__file__))
            for _ in range(5):
                base_dir = os.path.dirname(base_dir)
            
            paths = [
                os.path.join(base_dir, "data/stocks/stocks_index.json"),
                "data/stocks/stocks_index.json",
                "../data/stocks/stocks_index.json"
            ]
            for path in paths:
                if os.path.exists(path):
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        items = data.get("items", [])
                        # 建立映射：去空格后的名称 -> 标准代码 (Prefix)
                        mapping = {}
                        for item in items:
                            name = item.get("name", "")
                            symbol = item.get("symbol", "")
                            if name and symbol:
                                mapping[name.replace(" ", "")] = symbol
                        logger.info(f"Loaded {len(mapping)} stocks from {path}")
                        return mapping
            logger.warning("stocks_index.json not found in any search path.")
        except Exception as e:
            logger.error(f"Failed to load stocks_index.json: {e}")
        return {}

    async def analyze_images(self, image_data_list: List[bytes]) -> Dict[str, Any]:
        """
        Analyze a list of images and extract stock holding information.
        """
        if not self.client:
            raise ValueError("OCR Service is not configured (missing API Key)")

        all_holdings = []
        all_cash = []
        
        # (moved up in logic, will wrap the loop)
        
        for image_bytes in image_data_list:
            try:
                base64_image = base64.b64encode(image_bytes).decode("utf-8")
                
                prompt = (
                    "你是一个专业的金融数据提取助手。请从图片中提取股票持仓信息和资金状态。\n"
                    "要求：\n"
                    "1. 必须准确提取【股票名称】（或简称）和【持仓数量】。\n"
                    "2. 如果图片中包含【可用资金】（或‘可用’、‘可用余额’），请一并提取其数值。\n"
                    "3. 数量和金额请转换为纯数字，去掉逗号。\n"
                    "4. 【极其重要】注意识别小数点！图片中金额的小数点非常小，请仔细分辨（例如 1.00 不要误识别成 100）。\n"
                    "5. 【极其重要】不要遗漏带有 *ST 或 ST 前缀的股票，务必完整提取名称。\n"
                    "6. 图片中可能包含‘系统清算中’等提示条，请忽略提示条，专注于下方的列表数据。\n"
                    "7. 输出格式为 JSON 对象，包含：\n"
                    "   - 'holdings': 数组，字段：'name', 'quantity'\n"
                    "   - 'available_cash': 数值，如果未找到则为 null\n"
                    "注意：只需识别名称，无需识别代码。请务必仔细分辨数字。"
                )

                completion = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/jpeg;base64,{base64_image}"
                                    },
                                },
                                {"type": "text", "text": prompt},
                            ],
                        },
                    ],
                )
                
                content = completion.choices[0].message.content
                logger.debug(f"Qwen-VL response: {content}")
                
                # Extract JSON from potential markdown markers
                json_str = content
                if "```json" in content:
                    json_str = re.search(r"```json\s*(.*?)\s*```", content, re.DOTALL).group(1)
                elif "```" in content:
                    json_str = re.search(r"```\s*(.*?)\s*```", content, re.DOTALL).group(1)
                
                data = json.loads(json_str)
                
                # Extract available cash (take the max or latest if multiple images)
                if data.get("available_cash") is not None:
                    cash_val = float(data["available_cash"])
                    if cash_val > 0:
                        all_cash.append(cash_val)

                items = data.get("holdings", [])
                if isinstance(items, list):
                    for item in items:
                        name = str(item.get("name", "")).strip()
                        if not name:
                            continue
                            
                        # 通过名称索引匹配代码
                        clean_name = name.replace(" ", "")
                        symbol = self.stock_index.get(clean_name)
                        
                        # 模糊匹配策略：如果带 ST 的没匹配上，尝试去掉 ST 前缀再找
                        if not symbol:
                            # 移除常见前缀再试
                            fallback_name = re.sub(r'^(\*?ST|S|N|C|U)', '', clean_name)
                            if fallback_name != clean_name:
                                # 遍历索引寻找包含该后缀的
                                for idx_name, idx_sym in self.stock_index.items():
                                    if fallback_name in idx_name:
                                        symbol = idx_sym
                                        break
                        
                        if not symbol:
                            logger.warning(f"Could not find symbol for stock name: {name}")
                            
                        all_holdings.append({
                            "symbol": symbol,
                            "name": name,
                            "quantity": float(item.get("quantity") or 0)
                        })
                
            except Exception as e:
                logger.error(f"Failed to analyze holding image: {e}", exc_info=True)
                # Continue with next image instead of failing entirely
                
        # Deduplicate and merge quantities for same symbol
        merged = {}
        for r in all_holdings:
            sym = r["symbol"]
            if sym in merged:
                merged[sym]["quantity"] += r["quantity"]
            else:
                merged[sym] = r
                
        return {
            "holdings": list(merged.values()),
            "available_cash": max(all_cash) if all_cash else None
        }

