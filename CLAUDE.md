# CLAUDE.md

Karpathy 编程行为准则，减少 LLM 常见编码错误。偏重谨慎而非速度，简单任务自行判断。

## 1. 先想再写

**不要假设。不要隐藏困惑。表面权衡。先讨论逻辑再写代码。**

- 先明确陈述假设。不确定就问。
- 存在多种理解时，一一列出——不要悄悄选一个。
- 有更简单的方案就说。该反驳就反驳。
- 不清楚就停下来。说出困惑点。提问。
- **先讨论逻辑，用户认可后再写代码。** 不要自己闷头加用户没要求的维度（评分、ADX、突破强度），让用户参与设计决策。

## 2. 简单至上

**最少代码解决问题。不多写一行预判代码。**

- 不写超出需求的功能。
- 不为只调用一次的东西建抽象。
- 不做没被要求的"灵活性"或"可配置性"。
- 不为不可能发生的场景加错误处理。
- 写了 200 行能缩到 50 行？重写。

自问：「一个高级工程师会说这过度复杂吗？」会→简化。

## 3. 精准手术

**只碰必须改的。只清理自己搞乱的。**

- 不要"顺手优化"相邻代码、注释、格式。
- 不要重构没坏的东西。
- 保持一致风格，即使不是你惯用的。
- 发现无关的废弃代码→提出来，别直接删。

你的改动导致的孤儿代码（import/变量/函数）→自己清理。

测试标准：**每一行改动都能追溯到用户的需求。**

## 4. 目标驱动

**定义成功标准。循环直到验证通过。**

- "加个校验" → 「先写非法输入测试，再让它通过」
- "修这个 Bug" → 「先写能复现的测试，再修」
- "重构 X" → 「确保重构前后测试都通过」

多步骤任务，先列简要计划：
```
1. [步骤] → 验证: [检查点]
2. [步骤] → 验证: [检查点]
3. [步骤] → 验证: [检查点]
```

**这些准则生效的标志：** diff 中不必要的改动变少、因过度复杂导致重写的次数变少、澄清性问题出现在实现之前而非犯错之后。

## 5. Pine Script 语法坑（写指标时复习）

**行续接：`and` 必须在行尾，不能在下一行开头。**

```pine
// ❌ 编译报错: Mismatched input 'and' expecting 'end of line without line continuation'
isSignal = cond1
       and cond2
       and cond3

// ✅ 正确: and 在行尾续接
isSignal = cond1 and
   cond2 and
   cond3

// 短表达式可以直接写一行
engulfingBull = showEngulfing and not isBullish[1] and isBullish and close >= high[1]
```

**不支持一行多赋值（无分号）。**

```pine
// ❌ 编译报错
f1 = body[3]; f2 = body[2]

// ✅ 每行一个
f1 = body[3]
f2 = body[2]
```

**函数内引用全局 series 时注意偏移量。**

```pine
// avgBody 是当前K线的值
// 如果检查的是 Bar1 的数据(bodyVal[1])，要用 avgBody[1] 而非 avgBody
isStrongMother(bodyVal[1], upperWick[1], lowerWick[1], avgBody[1])
// 改为传参，避免函数内部误用当前值
```

**三元运算符建议写在一行。**

```pine
// ✅ 可以、但放一行更稳
val = a > b ? a : b
```

**`= na` 必须带类型转换，否则编译报错。**

```pine
// ❌ Value with NA type cannot be assigned
h0 = na

// ✅ float(na) 或 int(na) 显式声明类型
h0 = float(na)
h1 = int(na)
```

**数组读取用 `array.get()` 不要用 `[]`。两者不可混用。**

```pine
// ❌ Cannot call 'operator ==' with argument 'expr0'='call 'operator SQBR' (array<int>)'
if swType[0] == 1

// ✅ 统一用 array.get
if array.get(swType, 0) == 1
```

**v5 用 `math.abs`、`math.max`、`math.min`（带 math. 前缀）。**

**`color.new(#HEX, opacity)` — opacity 0~100，0 完全不透明，60 半透明。**

## 7. box 渲染与 Pine Script 执行模型

**`box.new` 的坐标稳定性：**
- `xloc.bar_index` + `bar_index` 比 `xloc.bar_time` + `time` 更稳定，不会在缩放时变化
- 不需要为了"更精确"用高级API，最简单的反而最稳
- 突破时用 `box.new(left=zoneStart, right=bar_index, ...)` 创建一次，之后不管怎么重算都一样

**`plot()` + `fill()` 作为 box 替代方案：**
- 活跃中的区域用 plot+fill 显示（没有 box 的各种限制）
- 完成后的区域用 box.new（固定坐标，只创建一次）
- fill 直接画在每个K线上，缩放不会变

**Pine Script 重算机制：**
- 每次缩放/滚动都会从 bar 0 重新执行整个脚本
- `var` 变量在重算开始时重置
- `box.new` 在重算时重新创建（旧的被清除）
- 不要在 `barstate.islast` 里画 box，会在不同"最后一根K线"上产生不同结果
- 在历史K线上画 box 会被限制（"too far from current bar"），用 `right=bar_index` 规避

**犯错地图（这个指标踩过的坑）：**
1. 用状态机追踪基底 → 太复杂，缩进和重置容易出错
2. `xloc.bar_time` → 理论上精确，实际缩放会变
3. `extend.right` + `box.set_right` → 互斥，不如只用一种
4. 空数组 `for i = 0 to -1` → 必须加 `if len > 0` 保护
5. `;` 一行多语句 → Pine 不支持
6. `box` 的上下边界用动态 swing 值更新 → 震荡前的老 swing 污染范围

**教训：能用 plot+fill 就别用 box。box 只在"确定已完成、固定坐标"的场景使用。**

## 8. 代码交付纪律

**改完代码后必须自己审查一遍才能给用户，不要让用户当编译器。**

具体流程：
1. 改完 → 检查语法（行续接、分号、类型）→ 检查逻辑（空数组、变量作用域）→ 自己过一遍完整代码
2. 确认没有明显问题再交给用户
3. 如果用户反馈编译错误，先理解错误原因再修，不要盲目试

这个指标犯的错误：每次改完直接让用户贴 TradingView，编译报错再修 → 浪费用户时间当编译器。应该改完后自己静态审查一遍。**第一次提交代码要尽量做到零编译错误。**

**提交前的审查清单（必须逐项检查）：**
1. `ta.` 前缀是否正确？（v5 函数名 vs v4）
2. 返回值类型对吗？（函数返回单值还是元组？需要解构吗？）
3. 数组访问会越界吗？（`[i]` 和 `[i+1]` 的循环边界）
4. 变量作用域对吗？（`if` 内声明的变量外部不可用）
5. 推调比等方向敏感的逻辑在上涨和下跌时都正确吗？
6. `var` 变量在重算时的行为是否符合预期？
7. 函数在最顶层声明了还是嵌套在 `if` 块里？

## 9. Pine Script 常见编译错误避坑

**`ta.dmi` 返回元组。**
```pine
// ❌ 不能直接赋值
adxVal = ta.dmi(14, 14)
// ❌ 也不能传 high/low/close
adxVal = ta.dmi(high, low, close, 14)

// ✅ 正确：解构赋值
[adxVal, diPlus, diMinus] = ta.dmi(14, 14)
```

**`for i = 0 to N` 中访问 `[i+1]` 时，N 要留出余量。**
```pine
// 访问 swHigh[i] 和 swHigh[i+1]，数组大小 = 2
// ❌ N = min(cnt1, cnt2) - 1 → i 跑到 1 时访问 [2] 越界
// ✅ N = min(cnt1, cnt2) - 2 → i 跑到 0 为止
```

**函数内的变量作用域。** Pine 的 `if/else` 块内声明的变量在块外不可见。需要在块外先声明再在块内用 `:=` 赋值。
```pine
// ❌ if 内声明，外部引用不到
if cond
    val = 1
// val 在外部不存在

// ✅ 外部先声明再赋值
val = 0
if cond
    val := 1
```

**`ta.sma`、`ta.atr` 等 v5 函数带 `ta.` 前缀，v4 不带。**

**`barstate.islast` 只在最后一根K线为真，常用于绘制一次性元素（table、label），但注意重算时也会触发。**

**`for` 循环空数组保护。** `for i = 0 to len - 1` 当 `len = 0` 时可能执行一次报越界，必须在循环外套 `if len > 0`。

```pine
// ❌ len=0 时可能报 Index 0 out of bounds
for i = 0 to array.size(arr) - 1
    val := array.get(arr, i)

// ✅ 加长度保护
len = array.size(arr)
if len > 0
    for i = 0 to len - 1
        val := array.get(arr, i)
```

## 6. 交易员隐性条件挖掘

**用户（交易员）提供的形态条件是"肉眼标准"，不是"计算机标准"。**

交易员说"这是个吞没形态"时，心里默认第二根明显更大，但不会专门说出来。代码按字面条件实现后，信号量够了但质量不行——因为隐性条件没挖出来。

**每次设计指标时，条件讨论完后必须多问几个问题：**

```
1. 反例挖掘："满足这些条件、但你看到也不会认为是这个形态的情况有哪些？"
2. 视觉直觉："这个形态肉眼看还有什么特征是自然而然、不需要特意说的？"
3. 信号质量："这些信号够强吗？有没有勉强算但实际你不想看到的？"
4. 强弱对比："关键K线和周围K线的大小对比要达到什么程度才叫'明显'？"
```

**让用户举反例比自己猜阈值更有效。** 比如问"什么样的情况勉强算吞没但其实不是你想要的"，比问"倍数设1.5还是2？"更能对齐预期。

## 10. 趋势结构设计原则（趋势识别指标专有）

**趋势的纯定义：HH+HL = 上升，LH+LL = 下降。**

- 不需要评分系统、ADX、推调比等额外维度来"确认"趋势。结构本身就是定义。
- 从震荡进入趋势时，必须验证N字结构的方向：
  - 上升 N 字 = 低→高→低→高（L→H→L→H），最新摆动必须是**高点**
  - 下降 N 字 = 高→低→高→低（H→L→H→L），最新摆动必须是**低点**
- 混合同步数组（swType/swPrice/swBar）比分开数组更可靠，能避免时间错位问题。

**状态机设计原则：**
- 保护位只在强势阶段更新，进入弱势后锁定
- CHoCH（性质改变）需要收盘价实体确认，影线不算
- 弱势阶段的保护位来自强势阶段（不随弱势新低更新）
- 对称设计：上升和下降方向的逻辑完全对称
  - 强势→弱势 都是 **LH+HL**（一端走弱，另一端结构还在）
  - 弱势→强势 都是 **对方方向的结构恢复**（HH+HL 恢复↑，LH+LL 恢复↓）
  - CHoCH 打破结构 → 返回震荡

**冷却期设计陷阱：**
- CHoCH 后需要冷却期防止同根K线重复进入同一方向
- **不要用 swCnt 比较（`swCnt > chUpSwCnt`）**——数组满 20 后 swCnt 不再增长，冷却永不失效
- **改用布尔标志**（`coolUp`/`coolDn`），新摆动点形成时重置：`if not na(phPrice) or not na(plPrice) → coolUp := false`
- `if` 语句在全局作用域不能有缩进，否则报 "Mismatched input 'if' expecting 'end of line without line continuation'"

**工作流程教训：**
- 不要在没有用户同意的情况下擅自换方案。如果当前方案有 bug，修复 bug，不是换思路。
- 讨论逻辑 → 用户确认 → 再改代码，顺序不能乱。

## 11. 震荡区识别指标设计原则

**震荡区边界更新 vs 突破退出是一体两面，必须同时设计。**
- 如果边界是动态更新的（每根新K线都可能扩大），"收盘超出边界"的退出条件在数学上有矛盾——收盘不会超过自己创造的最高值
- 必须在设计阶段就定好：边界什么时候更新、什么时候锁定、突破检测用哪套边界
- 解决方案：用不同数据源做不同的事——**摆动点（价格极值）定义边界**，**收盘价确认突破**
- 参考文章：[Dîngoreanu (2015)](https://www.utcluj.ro/media/documents/2015/Abilitare_Dinsoreanu.pdf) 的归一化市场位置函数

**不要在用户给的退出条件上叠加自己的中间状态。**
- ❌ 用户说"连续 2 根收盘超出=退出" → 我加"条件失效→冻结边界→然后等突破"共 3 个阶段
- ✅ 进入一条规则（ER < 0.35 满足）、退出一条规则（收盘连续超出），对称干净
- Karpathy 第 2 条的具体体现：**用户不要求的过渡状态，就是过度设计**

**学术调研的价值边际递减。**
- 调研 Ventura 2023 的 ML 集成模型 → 核心结论只是"ER 是区分度最高的单一特征"
- 调研的意义是**确认方案可行**，不是**找到最优方案让你改方向**
- 先设计再调研验证，而不是调研完了再设计

**震荡检测指标的三层架构：**
```
Detection（震荡期识别）→ ER + MA平坦
Definition（边界定义）→ 摆动点极值法 + 滚动窗口
Termination（退出检测）→ 连续同侧收盘突破
```
每层独立可调，改一层不影响其他层。

**Efficiency Ratio 公式：**
```pine
// ER = |close - close[N]| / sum(|close[i] - close[i-1]|, N)
erDirection = math.abs(close - close[erPeriod])
erVolatility = 0.0
for i = 0 to erPeriod - 1
    erVolatility += math.abs(close[i] - close[i + 1])
erValue = erVolatility > 0 ? erDirection / erVolatility : 1.0
// ER < 0.3-0.35 = 震荡（无净进展，来回折返）
```

## 12. Pine Script v5 编译错误实录（震荡指标踩的坑）

**`input.int` 的 `minval`/`maxval` 需要编译期常量，不能是另一个 `input` 变量。**
```pine
// ❌ maxval 必须是 const int
minBars = input.int(9, "最少", maxval=erPeriod)
// ✅ 写成固定值
minBars = input.int(9, "最少", maxval=14)
```

**`bgcolor()` 必须在全局作用域调用，不能在 `if/else` 块内。**
```pine
// ❌ 局部作用域不行
if inCons
    bgcolor(color.new(#FF9800, 92))
// ✅ 全局调用，颜色用条件表达式预计算
bgCol = inCons ? color.new(#FF9800, 92) : color.new(#000000, 100)
bgcolor(bgCol)
```

**v5 函数必须带命名空间前缀：`math.max` 不是 `max`，`math.min` 不是 `min`。**
- `math.abs`, `math.max`, `math.min`, `math.sum` — `math.` 开头的数学函数
- `ta.atr`, `ta.ema`, `ta.highest`, `ta.lowest`, `ta.pivothigh`, `ta.pivotlow` — `ta.` 开头的指标函数
- 漏一个就报 "Could not find function or function reference 'xxx'"

**函数体用隐式返回，不要用 `return`。**
```pine
// ❌ return 关键字可能导致编译不兼容
findBoundary() =>
    if cond
        return [val, true]
    return [na, false]

// ✅ 最后一个表达式是返回值
findBoundary() =>
    if cond
        [val, true]
    else
        [na, false]
```
