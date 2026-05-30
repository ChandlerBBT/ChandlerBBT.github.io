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
- `index.html`, `posts/`, `tags/`, `about/`: 生成后的 GitHub Pages 静态页面。

## 写作结构

建议每篇阶段性沉淀都覆盖四件事：

- 问题：这次想解决什么具体工作或学习问题。
- 方法：尝试了哪些工具、提示词、流程或文件结构。
- 结果：它带来了什么变化，哪些部分值得复用。
- 边界：它什么时候不适用，下一步还要验证什么。
