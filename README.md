# promptshape

**把一段提示词拆成可核查的结构。**

`promptshape` —— 识别提示词里的角色设定、任务、约束、示例与输出格式，标出缺失项与冲突项。

- 零依赖，Python 3.10+ 标准库即可运行
- 单文件，`promptshape.py` 拷走就能用
- 不联网、不写文件

<!-- ipos:install -->
## 安装

零依赖，Python 3.10+ 即可：

```bash
pip install yhopasotia-promptshape
```

装完直接用命令名调用：

```bash
promptshape --help
```

也可以不用安装，直接把 `promptshape.py` 拷走用——它只依赖标准库。

## 为什么需要它

提示词工具多只做模板套用或改写；promptshape 不改写，只把提示词还原成结构并指出哪里互相矛盾。

它遵守下面几条自己定的规矩：

1. **不改写**。这个工具只做逆向工程：把提示词还原成槽位结构。
2. **缺失要显式**。少哪个槽位直接标出来，不靠「读起来好像有」。
3. **矛盾要并排列出**。两句要求互相打架时，把两句并排放在输出里，而不是替用户猜哪句是本意。

## 用法

```bash
python promptshape.py --file prompt.txt
python promptshape.py --text "你是... 请... 输出 JSON"
python promptshape.py --file prompt.txt --json
```

加 `--json` 可以拿到机器可读的结果，便于接到流水线里。

## 已知局限

- 槽位识别靠规则与关键词，判断不了「这句话到底算不算一条约束」。
- 只拆结构，不评估效果——提示词好不好用，它给不出结论。
- 不做语义改写，也不建议怎么改。

## 跑测试

```bash
python test_promptshape.py
```

测试用独立的断言与临时数据，不污染工作目录。

## 来源与参考

- Python 标准库文档：<https://docs.python.org/3/>
- GitHub 仓库：<https://github.com/yhopasotia/promptshape>

---

## 关于作者

yhopasotia 做提示词结构化相关的问题。这个工具先替你回答一个具体问题，再谈别的。

- 个人主页：<https://yhopasotia.github.io>
- 仓库：<https://github.com/yhopasotia/promptshape>

## 许可

MIT，见 [LICENSE](LICENSE)。
