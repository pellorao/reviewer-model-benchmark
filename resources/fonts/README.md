# 页面离线字体

本目录的 `fonts.css` 包含可直接用于本地页面的完整 `@font-face` 声明. `build.py` 生成的页面通过 `<link>` 引用它. 字体请求只指向本目录文件, 页面加载不需要连接字体服务.

| CSS 字体名 | 文件与官方来源 | 字重与字形 | 许可证 |
| --- | --- | --- | --- |
| `Source Serif 4` | [Roman](https://raw.githubusercontent.com/adobe-fonts/source-serif/release/WOFF2/VAR/SourceSerif4Variable-Roman.ttf.woff2), [Italic](https://raw.githubusercontent.com/adobe-fonts/source-serif/release/WOFF2/VAR/SourceSerif4Variable-Italic.ttf.woff2) | `200 900`, 正体与斜体 | [SIL OFL 1.1](LICENSE-source-serif.md) |
| `Source Sans 3` | [Upright](https://raw.githubusercontent.com/adobe-fonts/source-sans/release/WOFF2/VF/SourceSans3VF-Upright.ttf.woff2), [Italic](https://raw.githubusercontent.com/adobe-fonts/source-sans/release/WOFF2/VF/SourceSans3VF-Italic.ttf.woff2) | `200 900`, 正体与斜体 | [SIL OFL 1.1](LICENSE-source-sans.md) |
| `Source Han Serif` | [简体中文区域可变 WOFF2](https://raw.githubusercontent.com/adobe-fonts/source-han-serif/release/Variable/WOFF2/TTF/Subset/SourceHanSerifCN-VF.ttf.woff2) | `250 900`, 正体 | [SIL OFL 1.1](LICENSE-source-han-serif.txt) |
| `Source Han Sans` | [简体中文区域可变 WOFF2](https://raw.githubusercontent.com/adobe-fonts/source-han-sans/release/Variable/WOFF2/TTF/Subset/SourceHanSansCN-VF.ttf.woff2) | `250 900`, 正体 | [SIL OFL 1.1](LICENSE-source-han-sans.txt) |

两套 `Source Han` 字体选用 Adobe 发布的 `CN` 区域子集, 适合本页的简体中文内容; 它们并非完整泛中日韩字符集. 六个 WOFF2 文件合计约 19.8 MB.
