# Chandler's AI Productivity Notes

这是 `ChandlerBBT.github.io` 的源码仓库，用来发布公开博客：把阶段性的 AI 提效研究、工作流拆解、skills 试验和实验复盘整理成可分享文章。

## 常用流程

1. 新建文章：

   ```powershell
   python tools/new_post.py "文章标题"
   ```

2. 编辑 `content/posts/` 下生成的 Markdown。

3. 生成静态站点：

   ```powershell
   python tools/build.py
   ```

4. 提交并发布：

   ```powershell
   .\tools\publish.ps1 -Message "Publish new post"
   ```

## 目录

- `content/posts/`: 博客 Markdown 源文件。
- `assets/`: 样式、脚本和图片资源。
- `tools/build.py`: 无第三方依赖的静态站点生成器。
- `tools/new_post.py`: 新文章模板生成器。
- `tools/import_bayes_rules.py`: Bayes Rules! 中文 Python 改写教程迁移脚本。
- `tools/check_bayes_rules.py`: Bayes Rules! 教程页质量检查脚本。
- `tools/deepseek_bayes_review.py`: DeepSeek 教程译文审校脚本。
- `index.html`, `posts/`, `tags/`, `about/`: 生成后的 GitHub Pages 静态页面。

## Bayes Rules! 教程维护

迁移或调整教程页后，先生成博客索引，再做教程质量检查：

```powershell
python tools/build.py
python tools/check_bayes_rules.py --strict
```

检查脚本会统计教程页、图片、代码块、剩余占位提示、疑似未完成代码块，以及本地链接和图片是否缺失。

需要逐章重译或审校时，先在当前终端设置 `DEEPSEEK_API_KEY`，再运行：

```powershell
python tools/import_bayes_rules.py --translator deepseek --model deepseek-v4-pro --batch-size 8 --api-timeout 90
python tools/deepseek_bayes_review.py --model deepseek-v4-pro --page chapter-2/index.html
```

DeepSeek 密钥只从环境变量读取，不写入仓库。

## 写作结构

建议每篇阶段性沉淀都覆盖四件事：

- 问题：这次想解决什么具体工作或学习问题。
- 方法：尝试了哪些工具、提示词、流程或文件结构。
- 结果：它带来了什么变化，哪些部分值得复用。
- 边界：它什么时候不适用，下一步还要验证什么。
