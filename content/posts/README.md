# 写作入口

每篇公开博客都放在这里，文件名建议使用：

```text
YYYY-MM-DD-english-or-chinese-slug.md
```

新建文章：

```powershell
python tools/new_post.py "文章标题"
```

本地生成站点：

```powershell
python tools/build.py
```

发布：

```powershell
.\tools\publish.ps1 -Message "Publish new post"
```
