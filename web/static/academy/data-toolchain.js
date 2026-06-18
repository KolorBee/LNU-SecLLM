// 安全学苑 - 工具链图谱数据
// 按「网络杀伤链 (Cyber Kill Chain)」阶段梳理 LNU-SecLLM 平台支持的安全工具，
// 帮助学员理解：工具不是孤立的，而是从侦察 → 利用 → 收尾串成一条完整的链条。
// 纯数据文件，挂载到全局，由 academy.js 渲染消费。
window.ACADEMY_TOOLCHAIN = {
    phases: [
        {
            id: 'recon',
            name: '信息收集',
            icon: '📡',
            desc: '在不触碰目标核心系统的前提下，尽可能摸清攻击面：存活主机、开放端口、子域名、网络资产与暴露在互联网上的服务。',
            tools: [
                { name: 'nmap', role: '端口与服务发现', desc: '业界事实标准的网络扫描器，能识别开放端口、服务版本、操作系统指纹，并通过 NSE 脚本做轻量探测。', tip: '链条起点：先用 nmap 画出目标的端口/服务地图，后续扫描与利用都以此为依据。' },
                { name: 'masscan', role: '大规模端口快扫', desc: '异步发包的超高速端口扫描器，可在短时间内扫遍大段 IP，适合先粗筛再用 nmap 精查。', tip: '面对 C 段或更大网段时先用 masscan 圈出存活端口，再把结果喂给 nmap 做精细识别。' },
                { name: 'rustscan', role: '快速端口预扫', desc: 'Rust 编写的极速端口扫描器，能在秒级找出开放端口并自动联动 nmap 做后续指纹识别。', tip: '当作 nmap 的“加速前置器”，先 rustscan 找端口、再交给 nmap 出详情。' },
                { name: 'arp-scan', role: '内网主机存活探测', desc: '基于 ARP 协议探测同一局域网内的存活主机，能绕过部分 ICMP 屏蔽，精准发现内网设备。', tip: '进入内网后第一步：用 arp-scan 摸清同网段还有哪些机器在线。' },
                { name: 'subfinder', role: '被动子域名枚举', desc: '聚合多个公开数据源被动收集目标子域名，速度快、噪声低，不直接接触目标。', tip: '从主域名扩展出大量子域名，扩大后续扫描的攻击面入口。' },
                { name: 'amass', role: '资产测绘与关联', desc: 'OWASP 出品的资产发现框架，结合 DNS 枚举、证书、API 等多源信息绘制目标的完整外部资产图。', tip: '想要“一张全景资产图”而不仅是子域名列表时，用 amass 做深度测绘。' },
                { name: 'fofa_search', role: '网络空间测绘', desc: '通过 FOFA 网络空间搜索引擎按指纹检索全球暴露资产，定位特定组件、设备或站点。', tip: '不发包就能定位目标资产：用 FOFA 语法搜出同指纹的相关系统。' }
            ]
        },
        {
            id: 'scan',
            name: '漏洞扫描',
            icon: '🔍',
            desc: '在已知资产与服务的基础上，主动探测可被利用的弱点：Web 漏洞、配置缺陷、敏感目录、注入点与防护边界。',
            tools: [
                { name: 'nuclei', role: '模板化漏洞探测', desc: '基于 YAML 模板的快速漏洞扫描器，社区模板覆盖 CVE、错误配置、敏感信息泄露等海量场景。', tip: '拿到资产清单后批量过一遍 nuclei，快速锁定“已知漏洞命中”的目标。' },
                { name: 'nikto', role: 'Web 服务器体检', desc: '经典的 Web 服务器扫描器，检测危险文件、过期组件、默认配置与常见服务器层问题。', tip: '面对一个 Web 站点先用 nikto 做一次全面体检，找出明显的低垂果实。' },
                { name: 'gobuster', role: '目录与资源爆破', desc: '高性能的目录/文件/子域名爆破工具，用字典枚举站点隐藏路径与后台入口。', tip: '通过爆破找出未公开的后台、备份文件或上传点，为利用阶段提供入口。' },
                { name: 'ffuf', role: '高速 Web 模糊测试', desc: '极快的 Web Fuzzer，可对路径、参数、虚拟主机等任意位置做字典模糊测试。', tip: '需要灵活定制 FUZZ 关键字位置时用 ffuf，比固定爆破更精准。' },
                { name: 'httpx', role: 'HTTP 探活与指纹', desc: '对大量主机批量探测 HTTP/HTTPS 存活情况，并采集状态码、标题、技术栈等指纹。', tip: '把 subfinder 的子域名列表过一遍 httpx，筛出真正存活的 Web 服务再深入。' },
                { name: 'wpscan', role: 'WordPress 专项扫描', desc: '专注 WordPress 的安全扫描器，枚举插件、主题、用户并匹配已知漏洞库。', tip: '识别到目标是 WordPress 时，用 wpscan 做针对性深挖。' },
                { name: 'wafw00f', role: 'WAF 识别', desc: '探测目标前端是否部署了 Web 应用防火墙以及具体厂商，帮助评估扫描与利用的绕过策略。', tip: '正式扫描前先 wafw00f 摸清防护，避免被 WAF 直接拦截并据此调整节奏。' }
            ]
        },
        {
            id: 'exploit',
            name: '漏洞利用',
            icon: '💥',
            desc: '把扫描阶段发现的弱点转化为实际控制：构造注入载荷、生成攻击载荷、调试逆向二进制，获取目标的初始访问权。',
            tools: [
                { name: 'sqlmap', role: 'SQL 注入自动利用', desc: '自动化 SQL 注入检测与利用工具，可探测注入点、拖库、读写文件乃至获取系统 shell。', tip: '在扫描发现可疑参数后，用 sqlmap 把“疑似注入”坐实为“数据/权限”。' },
                { name: 'dalfox', role: 'XSS 检测与利用', desc: '高性能的 XSS 扫描与参数分析工具，自动发现反射型/存储型跨站脚本并验证可执行载荷。', tip: '针对 Web 参数做 XSS 专项利用，验证前端信任边界是否被突破。' },
                { name: 'metasploit', role: '综合渗透利用框架', desc: '集成海量 exploit、payload 与辅助模块的渗透测试框架，是从漏洞到 shell 的核心引擎。', tip: '当 nuclei/nmap 命中已知 CVE 时，到 metasploit 找对应模块完成利用。' },
                { name: 'msfvenom', role: '攻击载荷生成', desc: 'Metasploit 配套的载荷生成器，可定制各平台 payload 并做编码免杀以适配目标环境。', tip: '需要一个反弹 shell 或木马载荷时用 msfvenom 生成，再投递到目标执行。' },
                { name: 'pwntools', role: '二进制漏洞利用开发', desc: 'CTF 与漏洞研究常用的 Python 利用框架，简化栈溢出、ROP、远程交互等利用脚本编写。', tip: '面对自研二进制服务时，用 pwntools 把逆向出的漏洞写成稳定的 exploit。' },
                { name: 'gdb', role: '动态调试分析', desc: 'GNU 调试器，配合插件可动态跟踪二进制执行、观察寄存器与内存，定位可利用的崩溃点。', tip: '利用开发前先用 gdb 调试，搞清崩溃如何被控制为代码执行。' },
                { name: 'radare2', role: '逆向工程分析', desc: '开源逆向工程框架，支持反汇编、静态分析与补丁，用于挖掘二进制中的漏洞逻辑。', tip: '静态读懂目标程序逻辑、找出可疑函数，再交给 gdb/pwntools 动手利用。' }
            ]
        },
        {
            id: 'privesc',
            name: '权限提升与后渗透',
            icon: '🚀',
            desc: '在已获得初始立足点后，枚举本地配置寻找提权路径，从普通用户跃升至高权限，并稳固对目标的控制。',
            tools: [
                { name: 'linpeas', role: 'Linux 提权枚举', desc: '自动化枚举 Linux 主机的提权线索：SUID、内核版本、计划任务、可写配置、敏感凭据等。', tip: '拿到低权限 shell 后第一时间跑 linpeas，让它替你列出所有可能的提权路径。' },
                { name: 'winpeas', role: 'Windows 提权枚举', desc: '针对 Windows 的提权信息收集脚本，检查服务权限、注册表、令牌、补丁缺失等弱点。', tip: '在 Windows 立足点上用 winpeas 找出错误配置，作为本地提权的依据。' },
                { name: 'mimikatz', role: '凭据抓取', desc: 'Windows 凭据提取的标志性工具，可从内存中导出明文密码、哈希、Kerberos 票据等。', tip: '提权到本地管理员后用 mimikatz 抓凭据，为横向移动准备“钥匙”。' },
                { name: 'volatility', role: '内存取证分析', desc: '内存镜像分析框架，可从内存转储中还原进程、网络连接、注入代码与残留凭据。', tip: '后渗透阶段分析获取到的内存样本，挖掘隐藏进程与遗留密钥。' },
                { name: 'exiftool', role: '元数据情报提取', desc: '读取并解析文档、图片等文件的元数据，常能挖出用户名、路径、软件版本等内部线索。', tip: '从战利品文件的元数据里捡取用户名/内网路径，辅助后续渗透。' },
                { name: 'steghide', role: '隐写数据提取', desc: '在图片/音频中隐藏或提取数据的隐写工具，用于挖掘藏匿的凭据与敏感文件。', tip: '怀疑文件中藏有夹带信息时用 steghide 提取，常见于取证与 CTF 场景。' }
            ]
        },
        {
            id: 'lateral',
            name: '横向移动与凭据',
            icon: '🔑',
            desc: '利用已获取的凭据与协议特性在内网中横向扩散：破解口令、伪造协议、绘制域内攻击路径，向核心资产逼近。',
            tools: [
                { name: 'hashcat', role: 'GPU 哈希破解', desc: '业界最快的密码哈希破解器，利用 GPU 算力对各类哈希做字典、规则与暴力破解。', tip: '把 mimikatz/responder 抓到的哈希交给 hashcat 还原成明文口令。' },
                { name: 'john', role: '口令离线破解', desc: 'John the Ripper 老牌密码破解工具，支持丰富的哈希类型与灵活的破解模式。', tip: '处理 /etc/shadow、压缩包等多样口令哈希时用 john，与 hashcat 互补。' },
                { name: 'impacket', role: '网络协议利用套件', desc: '一组 Python 网络协议库与脚本，可执行 SMB/WMI 远程命令、票据传递与凭据中继等横向操作。', tip: '拿到凭据后用 impacket（如 psexec/secretsdump）在内网横向执行与抓密码。' },
                { name: 'responder', role: 'LLMNR/NBT-NS 投毒', desc: '通过投毒 LLMNR、NBT-NS、mDNS 等广播协议诱捕内网中的认证请求，捕获 NetNTLM 哈希。', tip: '内网中静待并诱捕认证流量，抓到哈希再丢给 hashcat 破解。' },
                { name: 'bloodhound', role: '域攻击路径分析', desc: '用图论分析 Active Directory 中的权限关系，自动找出通往域管理员的最短攻击路径。', tip: '在 AD 环境中用 bloodhound 看清“从当前账号怎么走到域管”，规划横向路线。' },
                { name: 'nbtscan', role: 'NetBIOS 信息扫描', desc: '扫描网段内主机的 NetBIOS 名称、所属域/工作组与共享信息，辅助内网横向定位目标。', tip: '横向前用 nbtscan 摸清内网命名与归属，锁定值得攻击的主机。' }
            ]
        },
        {
            id: 'report',
            name: '分析与报告',
            icon: '📊',
            desc: '渗透收尾阶段：对获取的数据、容器与云配置做深度分析与合规审计，整理证据链并产出可交付的安全报告。',
            tools: [
                { name: 'trivy', role: '容器与依赖审计', desc: '全面的安全扫描器，检测容器镜像、文件系统与依赖中的漏洞和错误配置。', tip: '在收尾审计阶段扫描目标的镜像与依赖，量化风险并写入报告。' },
                { name: 'checkov', role: 'IaC 配置合规检查', desc: '针对 Terraform、Kubernetes 等基础设施即代码的静态分析工具，发现配置层面的安全与合规问题。', tip: '审计客户的 IaC 模板，把不合规配置整理成可整改的清单。' },
                { name: 'prowler', role: '云环境安全评估', desc: '面向 AWS 等云平台的安全评估与合规检查工具，覆盖 CIS、最佳实践等多种基准。', tip: '对云账户做基线评估，输出符合合规框架的差距分析报告。' },
                { name: 'scout-suite', role: '多云态势审计', desc: '多云安全审计工具，收集云配置并生成可视化的风险态势报告，定位高危资源。', tip: '跨多个云平台统一审计，用可视化报告向甲方清晰呈现风险全貌。' },
                { name: 'binwalk', role: '固件与文件分析', desc: '分析并提取固件镜像、二进制文件中嵌入的文件系统与数据，常用于取证与逆向证据梳理。', tip: '整理战利品固件/镜像时用 binwalk 拆解出内部组件，固化证据链。' },
                { name: 'foremost', role: '数据恢复与雕复', desc: '基于文件头/尾特征从磁盘或镜像中雕复（carve）出文件，用于取证证据提取。', tip: '从获取的磁盘镜像中恢复被删文件，作为报告中的取证佐证。' }
            ]
        }
    ]
};
