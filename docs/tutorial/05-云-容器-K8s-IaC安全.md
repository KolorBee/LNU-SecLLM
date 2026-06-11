# trivy

项目调用命令：`trivy`

用途：容器镜像、文件系统、Git 仓库、Kubernetes 配置、IaC 配置漏洞扫描。

安装：

```bash
sudo apt install -y wget apt-transport-https gnupg lsb-release
wget -qO - https://aquasecurity.github.io/trivy-repo/deb/public.key | sudo gpg --dearmor -o /usr/share/keyrings/trivy.gpg
echo "deb [signed-by=/usr/share/keyrings/trivy.gpg] https://aquasecurity.github.io/trivy-repo/deb $(lsb_release -sc) main" | sudo tee /etc/apt/sources.list.d/trivy.list
sudo apt update
sudo apt install -y trivy
```

验证：

```bash
trivy --version
```

简单测试：

```bash
trivy fs .
```

# docker-bench-security

项目调用命令：`docker-bench-security`

用途：按 Docker 安全基线检查本机 Docker 配置。

安装：

```bash
mkdir -p ~/tools
git clone https://github.com/docker/docker-bench-security.git ~/tools/docker-bench-security
sudo ln -sf ~/tools/docker-bench-security/docker-bench-security.sh /usr/local/bin/docker-bench-security
```

验证：

```bash
docker-bench-security -h
```

简单测试：

```bash
sudo docker-bench-security
```

# falco

项目调用命令：`falco`

用途：容器、主机和 Kubernetes 运行时行为检测。

Ubuntu/Debian 安装：

```bash
curl -fsSL https://falco.org/repo/falcosecurity-packages.asc | sudo gpg --dearmor -o /usr/share/keyrings/falco-archive-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/falco-archive-keyring.gpg] https://download.falco.org/packages/deb stable main" | sudo tee /etc/apt/sources.list.d/falcosecurity.list
sudo apt update
sudo apt install -y falco
```

验证：

```bash
falco --version
```

简单测试：

```bash
sudo falco --list
```

# checkov

项目调用命令：`checkov`

用途：扫描 Terraform、Kubernetes YAML、Dockerfile、GitHub Actions 等 IaC 配置。

安装：

```bash
pipx install checkov
```

如果只想安装到当前用户 Python 环境：

```bash
pip3 install --user checkov
```

验证：

```bash
checkov --version
```

简单测试：

```bash
checkov -d .
```

# prowler

项目调用命令：`prowler`

用途：云安全审计，常用于 AWS，也支持 Azure、GCP、Kubernetes 等环境。

安装：

```bash
pipx install prowler
```

如果只想安装到当前用户 Python 环境：

```bash
pip3 install --user prowler
```

验证：

```bash
prowler -v
```

AWS 凭据配置：

```bash
sudo apt install -y awscli
aws configure
```

简单测试：

```bash
prowler aws --list-checks
```

# scout-suite

项目调用命令：`scout`

用途：多云安全审计，常用于 AWS、Azure、GCP 等环境。

安装：

```bash
pipx install scoutsuite
```

如果只想安装到当前用户 Python 环境：

```bash
pip3 install --user scoutsuite
```

验证：

```bash
scout --help
```

AWS 简单测试：

```bash
scout aws --help
```

# cloudmapper

项目调用命令：`cloudmapper`

用途：AWS 环境资产枚举、网络关系分析和可视化。

安装：

```bash
mkdir -p ~/tools
git clone https://github.com/duo-labs/cloudmapper.git ~/tools/cloudmapper
cd ~/tools/cloudmapper
pip3 install --user -r requirements.txt
sudo ln -sf ~/tools/cloudmapper/cloudmapper.py /usr/local/bin/cloudmapper
```

验证：

```bash
cloudmapper --help
```

AWS 凭据配置：

```bash
sudo apt install -y awscli
aws configure
```

简单测试：

```bash
cloudmapper configure --help
```

# pacu

项目调用命令：`pacu`

用途：AWS 渗透测试与后渗透框架。

安装：

```bash
pipx install pacu
```

如果只想安装到当前用户 Python 环境：

```bash
pip3 install --user pacu
```

说明：项目中 [tools/pacu.yaml](/home/zhaoshuai/workspace_cyber/LNU-SecLLM/tools/pacu.yaml:3) 当前默认为 `enabled: false`，如果要让 CyberStrikeAI 调用它，需要先改为 `enabled: true`。

验证：

```bash
pacu --help
```

AWS 凭据配置：

```bash
sudo apt install -y awscli
aws configure
```
