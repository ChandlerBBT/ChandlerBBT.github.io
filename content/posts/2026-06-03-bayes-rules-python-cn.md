---
title: "Bayes Rules! 中文 Python 改写教程"
date: 2026-06-03
summary: "Bayes Rules! 的简体中文 Python 教程入口，覆盖贝叶斯建模、后验推断、回归、分类与分层模型。"
tags: ["贝叶斯统计", "Python", "教程"]
cover: "/assets/img/hero-workspace.png"
draft: false
---

这篇博客是一份可点击的教程入口：内容基于公开在线教材 [Bayes Rules! An Introduction to Applied Bayesian Modeling](https://www.bayesrulesbook.com/) 整理为简体中文，并统一使用 Python 生态示例。

> 来源作者为 Alicia A. Johnson、Miles Q. Ott、Mine Dogucu。来源内容采用 [Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License](https://creativecommons.org/licenses/by-nc-sa/4.0/) 授权；本版本按相同授权共享，仅用于非商业学习。

## 教程入口

[打开完整教程](/bayes-rules-python-cn/)

## 目录

- [前言](/bayes-rules-python-cn/foreword/)
- [序言](/bayes-rules-python-cn/preface/)
- [作者简介](/bayes-rules-python-cn/about-the-authors/)
- [第 1 章 贝叶斯图景总览](/bayes-rules-python-cn/chapter-1/)
- [第 2 章 贝叶斯公式](/bayes-rules-python-cn/chapter-2/)
- [第 3 章 Beta-二项贝叶斯模型](/bayes-rules-python-cn/chapter-3/)
- [第 4 章 贝叶斯分析中的平衡性与序贯性](/bayes-rules-python-cn/chapter-4/)
- [第 5 章 共轭族](/bayes-rules-python-cn/chapter-5/)
- [第 6 章 近似后验分布](/bayes-rules-python-cn/chapter-6/)
- [第 7 章 MCMC 的底层机制](/bayes-rules-python-cn/chapter-7/)
- [第 8 章 后验推断与预测](/bayes-rules-python-cn/chapter-8/)
- [第 9 章 简单正态回归](/bayes-rules-python-cn/chapter-9/)
- [第 10 章 回归模型评估](/bayes-rules-python-cn/chapter-10/)
- [第 11 章 扩展正态回归模型](/bayes-rules-python-cn/chapter-11/)
- [第 12 章 泊松回归与负二项回归](/bayes-rules-python-cn/chapter-12/)
- [第 13 章 Logistic 回归](/bayes-rules-python-cn/chapter-13/)
- [第 14 章 朴素贝叶斯分类](/bayes-rules-python-cn/chapter-14/)
- [第 15 章 分层模型的魅力](/bayes-rules-python-cn/chapter-15/)
- [第 16 章 无预测变量的正态分层模型](/bayes-rules-python-cn/chapter-16/)
- [第 17 章 含预测变量的正态分层模型](/bayes-rules-python-cn/chapter-17/)
- [第 18 章 非正态分层回归与分类](/bayes-rules-python-cn/chapter-18/)
- [第 19 章 加入更多层级](/bayes-rules-python-cn/chapter-19/)
- [参考文献](/bayes-rules-python-cn/references/)

## Python 生态约定

```python
import numpy as np
import pandas as pd
from scipy import stats
import pymc as pm
import arviz as az
import matplotlib.pyplot as plt
import seaborn as sns
```

## 质量说明

全书保留数学公式、图片、脚注、正文跳转和章节结构；统计术语按统一规范校正，代码示例统一采用 Python、PyMC、ArviZ、NumPy、pandas、SciPy、seaborn 与 scikit-learn。
