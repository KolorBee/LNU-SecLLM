// 安全学苑 - 安全资源库数据
// 纯数据模块：挂载到 window.ACADEMY_RESOURCES，供 academy.js 渲染。
// 前端会自动为所有链接补充 target=_blank rel=noopener，此处只产出数据。
window.ACADEMY_RESOURCES = {
    categories: [
        {
            id: 'knowledge',
            name: '权威知识库',
            icon: '📚',
            links: [
                { title: 'OWASP Top 10', url: 'https://owasp.org/www-project-top-ten/', desc: 'OWASP 官方维护的最严重 Web 应用安全风险榜单，入门 Web 安全必读。' },
                { title: 'OWASP Web Security Testing Guide', url: 'https://owasp.org/www-project-web-security-testing-guide/', desc: 'OWASP 官方 Web 安全测试指南，系统讲解渗透测试的方法论与用例。' },
                { title: 'OWASP Cheat Sheet Series', url: 'https://cheatsheetseries.owasp.org/', desc: 'OWASP 安全编码与防御速查表合集，开发与防护一线随手可查。' },
                { title: 'HackTricks', url: 'https://book.hacktricks.xyz/', desc: '社区驱动的渗透测试与红队技巧大全，覆盖各类服务、提权与漏洞利用。' },
                { title: 'PayloadsAllTheThings', url: 'https://github.com/swisskyrepo/PayloadsAllTheThings', desc: '各类漏洞利用 Payload 与绕过技巧的 GitHub 速查仓库，实战必备。' },
                { title: 'MITRE ATT&CK', url: 'https://attack.mitre.org/', desc: '全球公认的对手战术与技术知识库，用于理解攻击链与威胁建模。' }
            ]
        },
        {
            id: 'labs',
            name: '在线靶场 / 实训',
            icon: '🧪',
            links: [
                { title: 'PortSwigger Web Security Academy', url: 'https://portswigger.net/web-security', desc: 'Burp Suite 官方免费 Web 安全在线课程与靶场，系统学 Web 漏洞首选。' },
                { title: 'DVWA', url: 'https://github.com/digininja/DVWA', desc: '经典的可本地部署 PHP 靶场，分难度练习 SQL 注入、XSS 等常见漏洞。' },
                { title: 'OWASP Juice Shop', url: 'https://owasp.org/www-project-juice-shop/', desc: 'OWASP 现代化漏洞靶场，含闯关式挑战，适合体验真实业务漏洞场景。' },
                { title: 'VulHub', url: 'https://vulhub.org/', desc: '基于 Docker 的开源漏洞复现环境，一键搭建复现 CVE 与中间件漏洞。' },
                { title: 'BUUCTF', url: 'https://buuoj.cn/', desc: '国内热门 CTF 在线练习平台，海量历年赛题适合刷题入门与提升。' },
                { title: 'CTFHub', url: 'https://www.ctfhub.com/', desc: '中文 CTF 学习平台，提供技能树与在线靶场，按知识点循序渐进练习。' }
            ]
        },
        {
            id: 'community',
            name: '安全社区 / 博客',
            icon: '💬',
            links: [
                { title: '先知社区', url: 'https://xz.aliyun.com/', desc: '阿里云旗下安全技术社区，高质量原创漏洞分析与攻防研究文章聚集地。' },
                { title: 'FreeBuf', url: 'https://www.freebuf.com/', desc: '国内知名网络安全媒体与社区，覆盖资讯、教程与行业动态。' },
                { title: '安全客', url: 'https://www.anquanke.com/', desc: '奇安信旗下安全资讯与技术平台，关注漏洞情报与前沿研究。' },
                { title: '看雪学苑', url: 'https://www.kanxue.com/', desc: '老牌软件安全与逆向社区，逆向、二进制、CTF 学习的重要阵地。' },
                { title: 'Seebug Paper', url: 'https://paper.seebug.org/', desc: '知道创宇 404 实验室的技术博客，深度漏洞分析与原理剖析。' }
            ]
        },
        {
            id: 'tools',
            name: '工具官方文档',
            icon: '🛠️',
            links: [
                { title: 'Nmap 官方文档', url: 'https://nmap.org/docs.html', desc: '端口扫描与网络发现神器 Nmap 的官方文档，掌握信息收集基础。' },
                { title: 'sqlmap', url: 'https://github.com/sqlmapproject/sqlmap', desc: '自动化 SQL 注入检测与利用工具的官方仓库，附使用说明与 Wiki。' },
                { title: 'Nuclei 文档', url: 'https://docs.projectdiscovery.io/tools/nuclei/overview', desc: '基于 YAML 模板的快速漏洞扫描器官方文档，适合批量资产检测。' },
                { title: 'Metasploit 文档', url: 'https://docs.metasploit.com/', desc: '业界标准渗透测试框架的官方文档，了解利用模块与后渗透流程。' },
                { title: 'Burp Suite 文档', url: 'https://portswigger.net/burp/documentation', desc: 'Web 渗透测试主力工具 Burp Suite 的官方使用文档与功能讲解。' },
                { title: 'Wireshark 用户指南', url: 'https://www.wireshark.org/docs/wsug_html_chunked/', desc: '网络协议分析工具 Wireshark 官方手册，学习抓包与流量分析。' }
            ]
        },
        {
            id: 'ctf',
            name: 'CTF 与竞赛',
            icon: '🚩',
            links: [
                { title: 'CTFtime', url: 'https://ctftime.org/', desc: '全球 CTF 赛事日历与战队排名平台，了解赛程、查找 Writeup 的入口。' },
                { title: '攻防世界 XCTF', url: 'https://adworld.xctf.org.cn/', desc: 'XCTF 联赛官方在线练习平台，分方向提供新手到进阶的题目训练。' },
                { title: 'CTF Wiki', url: 'https://ctf-wiki.org/', desc: '中文 CTF 知识库，系统整理 Web、Pwn、Reverse、Crypto 等各方向知识点。' },
                { title: 'pwn.college', url: 'https://pwn.college/', desc: '亚利桑那州立大学开放的系统与二进制安全课程，从入门到进阶成体系。' }
            ]
        },
        {
            id: 'standards',
            name: '标准与法规',
            icon: '⚖️',
            links: [
                { title: '中华人民共和国网络安全法', url: 'https://www.cac.gov.cn/2016-11/07/c_1119867116.htm', desc: '国家网信办发布的网络安全法全文，从业与学习必知的法律底线。' },
                { title: '数据安全法', url: 'http://www.npc.gov.cn/npc/c2/c30834/202106/t20210610_311888.html', desc: '全国人大发布的数据安全法全文，了解数据处理活动的合规要求。' },
                { title: '个人信息保护法', url: 'http://www.npc.gov.cn/npc/c2/c30834/202108/t20210820_313088.html', desc: '我国个人信息保护的基础法律，明确个人信息处理规则与权利。' },
                { title: '信息安全等级保护 2.0 简介（国家标准全文公开）', url: 'https://openstd.samr.gov.cn/bzgk/gb/index', desc: '国家标准全文公开系统，可查询等保 2.0 等 GB/T 网络安全国家标准。' }
            ]
        }
    ]
};
