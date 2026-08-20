# mtf_voice_training

MTF 声音女性化练习手册(改进版)静态站点。

## 项目简介

本项目是一个**纯静态**单页网站,无需构建、无任何依赖:

- `index.html` — 手册主页面(全部内容与样式内联,分 7 章展示)
- `1.jpg` / `2.jpg` / `3.jpg` / `4.jpg` / `示意图.jpg` / `anatomy_base.png` — 手册插图
- `mineru_output/MTF声音女性化手册/` — 原始资料(PDF、Markdown 与 MinerU 提取的图片,页面插图按相对路径引用其中的 `images/` 目录)

所有资源引用均为**相对路径**,因此只要以项目根目录作为站点根目录启动任意静态服务器即可,不需要任何打包步骤。

## 本地部署

任选以下一种方式,在项目根目录执行。

### 方式一:Python(推荐,系统自带)

```bash
# 端口可任意指定,例如 8080
python -m http.server 8080
```

启动后访问 <http://localhost:8080> 即可。按 `Ctrl + C` 停止服务。

### 方式二:Node.js

```bash
# 使用 npx 临时运行,无需全局安装
npx serve -l 8080 .

# 或者
npx http-server -p 8080
```

### 方式三:VS Code Live Server 插件

安装 Live Server 插件后,右键 `index.html` → "Open with Live Server" 即可。

> 注意:也可以直接双击 `index.html` 用 `file://` 协议打开(纯静态相对路径,基本可用),但推荐通过 HTTP 服务器访问,行为与线上环境一致。

## 线上部署

项目为纯静态站点,可直接托管到任意静态托管平台。

### Cloudflare Pages

1. 将本项目推送到 GitHub / GitLab 仓库
2. 进入 Cloudflare Dashboard → Workers & Pages → Create → Pages → Connect to Git,选择该仓库
3. 构建配置填写:
   - **Framework preset**: `None`
   - **Build command**: 留空(无需构建)
   - **Build output directory**: `/`(即仓库根目录)
4. 部署完成后即可通过 `https://<项目名>.pages.dev` 访问

也可以使用命令行直接上传(需先安装 [Wrangler](https://developers.cloudflare.com/workers/wrangler/) 并登录):

```bash
npx wrangler pages deploy . --project-name=mtf-voice-training
```

### GitHub Pages

1. 仓库 Settings → Pages
2. Source 选择 `main` 分支、根目录 `/`
3. 保存后访问 `https://<用户名>.github.io/<仓库名>/`

### Vercel

本项目是纯静态站点,Vercel 可以"零配置"直接部署,不需要写任何构建命令。推荐通过 GitHub 仓库连接部署,这样每次 `git push` 都会自动发布新版本。

#### 方式一:通过 Git 仓库部署(推荐,自动持续部署)

前提:项目已推送到 GitHub(或 GitLab / Bitbucket)仓库,例如 `https://github.com/sideonkeibulllll/mtf_voice_training.git`。

1. 打开 <https://vercel.com> 并注册 / 登录(可直接用 GitHub 账号登录)
2. 点击右上角 **Add New… → Project**
3. 在 **Import Git Repository** 列表中找到 `mtf_voice_training` 仓库,点击 **Import**
   - 如果列表里没有,点击 **Adjust GitHub App Permissions** 授权 Vercel 访问该仓库
4. 配置部署项(关键步骤):
   - **Framework Preset**: 选择 `Other`(或保持默认,Vercel 会自动识别为静态站点)
   - **Root Directory**: 保持 `./`(仓库根目录)
   - **Build Command**: **留空**(纯静态站点,无需构建)
   - **Output Directory**: 留空或填 `./`(默认输出目录即项目根目录)
5. 点击 **Deploy**,等待约十几秒即可完成
6. 部署成功后,访问分配的默认域名 `https://<项目名>.vercel.app` 即可

后续每次向该仓库 `git push`,Vercel 都会自动构建并发布新版本;每次部署都会生成一个唯一的预览 URL,正式域名始终指向最新的 Production 部署。

#### 方式二:使用 Vercel CLI 直接部署(不经过 Git)

适合本地直接上传文件、不经 Git 仓库的场景:

```bash
# 1. 安装 Vercel CLI(需要 Node.js)
npm i -g vercel

# 2. 在项目根目录执行,首次使用会引导登录
vercel

# 3. 按提示操作:
#    Set up and deploy? → Y
#    Which scope? → 选择你的账号
#    Link to existing project? → N(首次)
#    What's your project's name? → mtf-voice-training(可自定义)
#    In which directory is your code located? → ./(直接回车)
#    这些命令会创建... → 全部 Y(自动识别为静态项目)

# 4. 部署为生产环境(正式域名指向该版本)
vercel --prod
```

CLI 会自动识别这是静态站点(无需构建命令),直接把当前目录的文件全部上传。首次 `vercel` 生成的是预览 URL,加 `--prod` 才会更新正式域名。

#### 常用后续操作

- **绑定自定义域名**:项目设置 → Domains → Add,按提示添加 CNAME 记录
- **回滚版本**:项目 Deployments 列表中,在历史版本右侧菜单选择 **Promote to Production**
- **手动重新部署**:Deployments → 最新记录 → Redeploy
- **环境变量**:本项目为纯静态站点,无需配置任何环境变量

> 注意:`mineru_output/` 目录中的原始 PDF 与 JSON 文件也会一并上传(页面插图依赖其中的 `images/` 目录)。如果只想上传必要文件,可在项目根目录添加 `.vercelignore` 排除 `*.pdf`、`*.json` 等大文件,但**不要**排除 `images/` 目录,否则页面插图会 404。

### Netlify

与 Vercel 类似:导入 Git 仓库,构建命令留空、发布目录设为项目根目录(`./`)即可;也可用 CLI `netlify deploy` 直接上传当前目录。

## 目录结构

```
mtf_voice_training-main/
├── index.html                  # 站点入口(单文件页面)
├── 1.jpg / 2.jpg / 3.jpg / 4.jpg
├── 示意图.jpg
├── anatomy_base.png
└── mineru_output/
    └── MTF声音女性化手册/
        ├── MTF声音女性化手册.md   # 手册 Markdown 源文档
        ├── ..._origin.pdf        # 原始 PDF
        └── images/               # MinerU 提取的插图(页面按相对路径引用)
```
