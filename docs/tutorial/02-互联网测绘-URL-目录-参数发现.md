# gau

项目调用命令：`gau`

安装：

```bash
go install github.com/lc/gau/v2/cmd/gau@latest
```

如果提示找不到 `gau`，确认 Go 工具目录已经加入 PATH：

```bash
export PATH="$PATH:$HOME/go/bin"
```

验证：

```bash
gau --version
```

简单测试：

```bash
echo example.com | gau
```

# hakrawler

项目调用命令：`hakrawler`

安装：

```bash
go install github.com/hakluke/hakrawler@latest
```

验证：

```bash
hakrawler -h
```

简单测试：

```bash
echo https://example.com | hakrawler
```

# katana

项目调用命令：`katana`

安装：

```bash
go install github.com/projectdiscovery/katana/cmd/katana@latest
```

验证：

```bash
katana -version
```

简单测试：

```bash
katana -u https://example.com -silent
```

# paramspider

项目调用命令：`paramspider`

安装：

```bash
pipx install git+https://github.com/devanshbatham/paramspider.git
```

如果没有安装 `pipx`：

```bash
sudo apt install -y pipx git
pipx ensurepath
source ~/.bashrc
```

验证：

```bash
paramspider --help
```

简单测试：

```bash
paramspider -d example.com
```

# uro

项目调用命令：项目内 Python 调用

安装：

```bash
pipx install uro
```

如果 `pipx` 安装失败，可以改用用户目录安装：

```bash
pip3 install --user uro
```

验证：

```bash
uro --help
```

简单测试：

```bash
printf "https://example.com/a?id=1\nhttps://example.com/a?id=2\n" | uro
```

# qsreplace

项目调用命令：`python3` 内置脚本

说明：项目 YAML 中已经内置轻量实现，通常只需要系统存在 `python3`，不需要额外安装 `qsreplace` 命令。

验证：

```bash
python3 --version
```

如果你希望同时安装原版 Go 工具，方便在终端手工使用：

```bash
go install github.com/tomnomnom/qsreplace@latest
```

手工验证：

```bash
echo "https://example.com/?q=old" | qsreplace test
```

# anew

项目调用命令：`python3` 内置脚本

说明：项目 YAML 中已经内置轻量实现，通常只需要系统存在 `python3`，不需要额外安装 `anew` 命令。

验证：

```bash
python3 --version
```

如果你希望同时安装原版 Go 工具，方便在终端手工使用：

```bash
go install github.com/tomnomnom/anew@latest
```

手工验证：

```bash
printf "a\nb\n" | anew /tmp/anew-test.txt
```

# dirb

项目调用命令：`dirb`

安装：

```bash
sudo apt install -y dirb
```

验证：

```bash
dirb
```

简单测试：

```bash
dirb http://example.com
```

# dirsearch

项目调用命令：`dirsearch`

安装：

```bash
pipx install dirsearch
```

如果没有安装 `pipx`：

```bash
sudo apt install -y pipx
pipx ensurepath
source ~/.bashrc
```

验证：

```bash
dirsearch --help
```

简单测试：

```bash
dirsearch -u http://example.com
```

# gobuster

项目调用命令：`gobuster`

安装：

```bash
sudo apt install -y gobuster
```

如果系统软件源版本太旧，可以用 Go 安装：

```bash
go install github.com/OJ/gobuster/v3@latest
```

验证：

```bash
gobuster version
```

简单测试：

```bash
gobuster dir -u http://example.com -w /usr/share/wordlists/dirb/common.txt
```

# feroxbuster

项目调用命令：`feroxbuster`

安装：

```bash
sudo apt install -y feroxbuster
```

如果软件源没有该包，可以用 Cargo 安装：

```bash
cargo install feroxbuster
```

验证：

```bash
feroxbuster --version
```

简单测试：

```bash
feroxbuster -u http://example.com
```

# ffuf

项目调用命令：`ffuf`

安装：

```bash
sudo apt install -y ffuf
```

如果系统软件源没有该包，可以用 Go 安装：

```bash
go install github.com/ffuf/ffuf/v2@latest
```

验证：

```bash
ffuf -V
```

简单测试：

```bash
ffuf -u http://example.com/FUZZ -w /usr/share/wordlists/dirb/common.txt
```
