# 第三方组件与素材许可（模板）

> 本文件只列“会进成片 / 会进工程”的第三方依赖。本仓库自身代码为 MIT。
> 开源发布前请逐项核对并补全版本号与链接。

## 随仓库分发

| 组件 | 许可 | 说明 |
|---|---|---|
| 本仓库 `skills/`、`mcp/`、`install.sh` | MIT | 作者原创代码 |
| 字体（Noto Sans SC / Noto Serif SC / Instrument Serif / JetBrains Mono） | SIL OFL 1.1 | 若随示例分发，保留 OFL.txt |

## 安装时获取，不随仓库分发

| 组件 | 许可 | 获取方式 | 备注 |
|---|---|---|---|
| web-video-presentation (wvp) | MIT | `install.sh --with-wvp` 稀疏克隆 | 上游 ConardLi/garden-skills |
| Playwright / Chromium | Apache-2.0 | `npm i -D playwright` | 录屏用；也可复用本机 Edge |
| FFmpeg | LGPL/GPL（看构建） | 系统安装 | 只用 CLI，不静态链接 |
| IndexTTS 2.0 分发包 | 按其自带许可 | 用户本地安装 | 本仓库只调用本地 HTTP 接口，不分发模型 |
| edge-tts（可选降级） | GPL-3.0 | `pip install edge-tts` | 作为无 GPU 机器的兜底；注意 GPL 传染边界（仅进程调用） |
| dsh-agent-teams（可选） | MIT | 插件安装 | 章节并行 |

## EAC design world / 动效库（可选插件，不随仓库分发）

| 组件 | 许可 | 使用边界 |
|---|---|---|
| motion-promo-film / motion-promo-film-v2 | `local-skill-see-notices`（插件内声明） | 只读取本机已安装版本；不复制其源码进本仓库 |
| video-shotcraft（150 条动效） | Apache-2.0 | 只取“运动规律”复刻；成片与文档需署名 Wei Yihao / video-shotcraft |
| onetake `motion.js` | PolyForm Noncommercial | **商用需授权**；本仓库默认不启用 |
| EAC 内置模板/示例成片 | 依插件许可 | 不直接交付他人示例成片 |

## 成片署名建议

片尾或简介固定一行：

```
动效参考：video-shotcraft (Apache-2.0, Wei Yihao) · 模板风格：EAC motion-promo-film
配音：IndexTTS 2.0（本地）· 字体：Noto Sans SC / Instrument Serif (OFL)
```

## 待办

- [ ] 给每个上表条目补版本号与上游 URL
- [ ] 确认 edge-tts 的 GPL 边界（仅子进程调用是否可接受）并在 README 声明
- [ ] 确认 IndexTTS 模型权重许可是否允许商用
- [ ] 示例成片若含第三方素材，单独列 `CREDITS.md`
