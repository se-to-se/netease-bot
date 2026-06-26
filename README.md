# Netease TG Bot

Telegram 机器人，发送网易云音乐链接即可获得歌词翻译 + 热评翻译，支持中日俄英四种语言。

## 功能

- 发送标准链接 (`music.163.com`) 或短链接 (`163cn.tv`) 均可识别
- 四种翻译语言：中文 / English / 日本語 / Русский
- 翻译歌词（完整多行）+ 前 5 条热评
- `/start` 选择界面语言，全程多语言 UI
- `/help` 查看 6 张教程图片
- 彩蛋：输入 `gift` 触发隐藏回复

## 技术栈

| 层 | 技术 |
|----|------|
| Bot 框架 | python-telegram-bot |
| 翻译 | 百度翻译 API（免费版，200万字符/月） |
| 数据 | NeteaseCloudMusicApiEnhanced（自部署） |
| 部署 | Railway + Docker |

## 项目结构

```
netease-tg-bot/
├── bot.py           # Bot 主逻辑、i18n、回调处理
├── config.py        # 环境变量读取
├── netease.py       # 网易云 API（链接解析/歌词/评论）
├── translate.py     # 百度翻译封装
├── Dockerfile       # Railway 部署
├── requirements.txt # Python 依赖
├── railway.json     # Railway 配置
├── .env.example     # 环境变量模板
└── tutorial/        # /help 教程图片（用户自备）
```

## 环境变量

| 变量 | 说明 |
|------|------|
| `TG_BOT_TOKEN` | Telegram Bot Token（找 @BotFather） |
| `BAIDU_APP_ID` | 百度翻译 APP ID |
| `BAIDU_SECRET_KEY` | 百度翻译密钥 |
| `NETEASE_API_BASE` | 网易云 API 地址（自部署的 api-enhanced） |
| `TUTORIAL_IMAGES` | 教程图片 URL，逗号分隔（可选） |

## 部署

1. Fork 本仓库
2. 在 [Railway](https://railway.app) 创建项目 → Deploy from GitHub
3. 同时部署 [NeteaseCloudMusicApiEnhanced](https://github.com/NeteaseCloudMusicApiEnhanced/api-enhanced) 作为 API 服务
4. 在 Railway Variables 中填入上述环境变量
5. 在 @BotFather 设置命令：
   ```
   start - 开始使用，选择语言
   help - 查看教程图片
   ```

## 备注

- 网易云 API 使用社区增强版，非官方接口
- 百度翻译免费版限 1 QPS，代码已做延迟处理
- 语言偏好存储在内存中，Railway 重启后重置为中文
