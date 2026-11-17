# 贡献指南

## 红线：内容隐私

本仓库定位是**引擎 + 匿名示例**。`.gitignore` 默认排除一切真实 deck 内容
（`decks/`、`assets/`、`src/slides`、`src/shell.html`、`docs/本地笔记/`，白名单只放行 `sample-deck`）。

**第二道防线**：`tools/privacy_check.py` 会扫描暂存文件的路径与内容，命中私人标记
（真名 / 个人域名 / 私有 deck 标题等）即拒绝提交。维护者本机已安装
`.git/hooks/pre-commit`（`python3 tools/privacy_check.py --install-hook` 可重装）。
绕过它（`git commit --no-verify`）等同违反本红线。

- ❌ 不要在 PR / issue / 截图里出现你的真实汇报内容、姓名、机构品牌、内部链接
- ❌ 不要把 `.gitignore` 排除的个人文件「顺手」加进暂存区
- ✅ 演示新特性请改 `src-sample/`，或新建 `src-example-*/`（同样匿名）

## 改动约定

- **代码风格**：与周围代码一致——中文注释、注释密度克制、工具脚本带 docstring 用法示例；
  Python 兼容 3.9（禁止 PEP 604 `X | None` 注解），Node 仅用标准库
- **引擎改动**（`src/js/deck.js`、`src/css/*`）：所有 deck 共享这一份运行时，
  改完跑 `node build.mjs` + `python3 tools/check_slides.py` + `python3 tools/test_deck.py`
- **导入 pipeline**（`tools/import_pptx.py`、`tools/pptx_*.py`）：每个修复工具保持
  `main(src, dst, 参数)` 可导入复用的形态；改动默认配方前先在多套真实 PPTX 上对比补字数
- **serve_deck.py 的 Host 守卫不许放松**（站点可能被反代到公网且无鉴权）

## 提交前自检

```bash
node build.mjs                        # 拼装无报错
python3 tools/check_slides.py         # 体检退出码 0
python3 tools/test_deck.py            # 交互自测全过
git status                            # 暂存区没有个人内容
```
