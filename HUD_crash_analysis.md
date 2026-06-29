================================================================================
HUD Overlay 崩溃根因分析报告
================================================================================

一、关键发现
================================================================================

1. setHUDEnabled: 函数特征 (0x1DD98-0x1DF38)
   - 该函数**完全忽略 w2 (BOOL) 参数**，而是用 self==nil 来判断启用/禁用
   - self != nil → ENABLE 路径 (w2=1 在关键调用中)
   - self == nil → DISABLE 路径 (w2=0 在关键调用中)
   - 有栈金丝雀 (stack canary) 保护
   - 内部通过类名字符串加载一个类并创建实例，设置动画 block

2. tapMainButton: 原始行为 (0x9BB24-0x9BCE4)
   原始代码流程：
   a) 标准函数序言 (stp x20,x19; stp x29,x30; add x29,sp,#0x50)
   b) 调用 [self isHUDEnabled] (加载 selector @0x1003AD2D0)
   c) tbz w0,#0 → 如果 isHUDEnabled==NO，跳转到 showActivationDialog 路径
   d) 如果 isHUDEnabled==YES:
      - 调用某个验证方法 (selector @0x1003ACFC0)
      - eor w2, w0, #1 → 翻转结果
      - 调用 [self setHUDEnabled:!result]
   e) 大量 UI 更新/动画代码

3. 现有 patch 的状态 (capstone dump 显示)
   ```
   0x9BB24: mov w2, #2          ; 42 00 80 52
   0x9BB28: b   #0x10001dd98    ; 9c 08 fe 17
   ```
   这是 8 字节的 patch，并非用户描述的 16 字节完整版。
   注意 w2=2 而非 w2=1（虽然 w2 的值其实被 setHUDEnabled 忽略）。

4. setHUDEnabled: 不在任何 ObjC 方法列表中！
   经搜索 RootViewController(61方法)、ImGuiHudView(24方法)、HUDRootViewController(17方法)、
   HUDMainApplication、HUDMainApplicationDelegate 等所有方法列表，
   没有任何 IMP 解析到 0x1DD98。该函数可能是：
   - 通过 runtime 动态添加的方法
   - 一个 C 函数而非 ObjC 方法
   - 被替换过的残留代码

二、崩溃根因分析
================================================================================

崩溃最可能的根因是以下因素的组合：

A.【主要】跳过必要的前置检查
   - 原始 tapMainButton 先检查 isHUDEnabled，只有 HUD 已激活时才调用 setHUDEnabled:
   - 如果 HUD 未激活，走 showActivationDialog 路径
   - Patch 无条件直接调用 setHUDEnabled:YES，可能访问了未初始化的状态
   - setHUDEnabled: 内部通过类名动态加载类，如果类尚未注册会导致崩溃

B.【次要】x0 (self) 的值不正确
   - setHUDEnabled: 用 self==nil 来决定启用/禁用
   - 从 tapMainButton 传入时 self=RootViewController (非nil)
   - 原本可能期望 self=ImGuiHudView 或其他特定对象
   - 虽然非 nil 走了 ENABLE 路径，但内部操作可能依赖 self 的类型

C.【次要】绕过 objc_msgSend 直接 B 指令跳转
   - 正常 ObjC 方法调用通过 objc_msgSend，运行时会设置方法缓存、
     autorelease pool、thread-local 状态
   - 直接 B 指令跳转绕过了这些
   - 函数内部的 objc_msgSend 调用（加载类、创建对象等）可能因缺少上下文而失败

D.【次要】w2 被设为 2 而非 1
   - 虽然 setHUDEnabled: 忽略 w2，但如果某条内部路径间接使用了它可能出问题

三、函数 0x1DD98 详细代码流分析
================================================================================

setHUDEnabled:(0x1DD98) 的完整执行路径：

第一阶段 (0x1DD98-0x1DE20) - 初始化：
  - sub sp, #0x60          ; 分配 96 字节栈帧
  - 保存 x20,x19,x29,x30
  - 加载栈金丝雀
  - adrp x0, #0x100375000; add x0, #0x739  ; x0 = 类名字符串地址
  - bl objc_getClass(?)    ; 加载某个类
  - add x0, sp, #0x18; bl alloc/init  ; 创建对象在 sp+0x18
  - 调用多个初始化方法 (w1=0x63, w2=1; w1=0; w1=0)
  - str wzr, [sp, #0x14]   ; 局部变量 = 0
  - bl some_func(0, &local)
  - bl some_func2(1, local)
  - str x0, [0x1003AE250]  ; 存储到全局变量 ⚠️

第二阶段 - nil 检查 (0x1DE24):
  - cbz w19, DISABLE_PATH  ; w19 == self (来自 x0)
  - self != nil → ENABLE 路径

ENABLE 路径 (0x1DE28-0x1DE94):
  - 配置对象 sp+0x18 (w1=0, w1=2)
  - 从全局加载 [0x1003AE250] → x1
  - 加载字符串地址 0x10037512D → x8
  - stp x1, x8, [sp, #0x20]  ; 构建 block/上下文结构
  - str xzr, [sp, #0x30]
  - 加载另一个全局 [0x1003A4170] → x5
  - add x0, sp, #0x10    ; 输出参数
  - add x3, sp, #0x18    ; 对象
  - add x4, sp, #0x20    ; block/上下文
  - mov x2, #0
  - bl key_setup_func(x0, ?, 0, obj, block)  ; ⚠️ 关键调用，x1 未显式设置!
  - 如果成功，ldr w0, [sp, #0x10]; add x1, sp, #0xc; mov w2, #1
  - bl final_func(w0, &output, 1)  ; 启用 HUD

DISABLE 路径 (0x1DE98-0x1DF10):
  - 加载全局 view [0x1003AD4F8]
  - animateWithDuration:0.25 (带完成 block)
  - 类似 ENABLE 路径的 block 设置
  - final_func 中 w2=0 (禁用)
  - 循环等待条件满足 (mvn; tst; b.eq)

第三阶段 - 清理:
  - 栈金丝雀检查
  - 恢复寄存器并返回

⚠️ 关键风险点:
  - 0x1DE40: ldr x1, [x20, #0x250] — 从全局加载，如果全局未正确初始化则 x1=垃圾值
  - 0x1DE70: bl key_func — x1 保持全局值未重新设置，可能传递无效参数
  - 0x1DDC4: bl objc_getClass — 如果类不存在返回 nil，后续操作崩溃

四、修复方案建议
================================================================================

方案 A：【推荐】通过 objc_msgSend 正确调用 setHUDEnabled:YES
----------------------------------------------------------------
不直接 B 到 IMP，而是构造正确的 objc_msgSend 调用：

patch 代码（替换 tapMainButton 前 16 字节）:
  ; x0 已经 = self (RootViewController)
  ADRP X1, page_isHUDEnabled_selref   ; X1 = selref for isHUDEnabled
  LDR  X1, [X1, #offset]              ; X1 = "isHUDEnabled" selector
  BL   _objc_msgSend                  ; 调用 [self isHUDEnabled]
  ; 现在 x0 = 返回值 (BOOL)
  ; 如果返回 YES，说明 HUD 系统已就绪
  CBZ  W0, skip_hud                   ; 如果 NO，跳过
  
  ; 找到正确的 self (可能是 self.hudRootViewController 或 ImGuiHudView)
  ; 通过 ivar 偏移加载
  LDR  X0, [X19, #hudView_offset]     ; X0 = self->hudView (需要确定 ivar 偏移)
  
  ADRP X1, page_setHUDEnabled_selref  ; X1 = selref for setHUDEnabled:
  LDR  X1, [X1, #offset]              ; X1 = "setHUDEnabled:" selector
  MOV  W2, #1                         ; W2 = YES
  BL   _objc_msgSend                  ; [hudView setHUDEnabled:YES]
  
skip_hud:
  ; 如果需要，继续原始 tapMainButton 的其余逻辑
  B    original_tapMainButton_continue

或者更简单：找到正确的 HUD 对象和 setHUDEnabled: 的实际 IMP

方案 B：找出 setHUDEnabled: 的真实 IMP 地址
----------------------------------------------------------------
0x1DD98 可能不是运行时实际被调用的 setHUDEnabled: IMP。
需要：
1. 运行时用 Hopper/IDA 附加调试，在 setHUDEnabled: 上设断点
2. 查看实际被调用的地址
3. 或者在 RootViewController 方法列表中定位 setHUDEnabled: entry

查看方法列表 entry 计算：
  RootViewController baseMethods @0x1000AC7E0, 61 entries, entsize=12
  找到 name="setHUDEnabled:" (selref 指向 0x100373FE1) 的那个 entry，
  其 imp 字段就是真正的实现地址。

方案 C：直接操作 ImGuiHudView
----------------------------------------------------------------
绕过 setHUDEnabled:，直接控制 ImGuiHudView 的可见性：

1. 找到 RootViewController 中存储 ImGuiHudView 的 ivar
   (RootViewController instanceSize=544, 需要确定 offset)
2. 直接设置 ImGuiHudView.hidden = NO
3. 或者调用 ImGuiHudView 的其他公开方法

方案 D：完整模拟原始 tapMainButton 逻辑
----------------------------------------------------------------
不跳过函数序言和检查，而是 patch 条件判断：

原始代码关键分支：
  0x9BB48: tbz w0, #0, #0x9BC24  ; 如果 isHUDEnabled==NO → 跳走

Patch 方案：
  0x9BB48: NOP                    ; 去掉条件跳转，强制走 HUD 切换路径

然后在 0x9BB5C 处:
  eor w2, w0, #1  →  mov w2, #1  ; 强制 w2=YES (启用 HUD)

这样保留所有前置检查和初始化，只修改分支逻辑。

五、下一步行动建议
================================================================================

1. 【紧急】确认二进制中 0x9BB24 当前的实际字节
   - 用 xxd 或 hexdump 检查前 16 字节
   - 确认是否已应用了错误/不完整的 patch

2. 【关键】找到 setHUDEnabled: 的真正确认 IMP
   - 遍历 RootViewController 方法列表找到 setHUDEnabled: entry
   - 或者用 Frida/debugger 在运行时捕获实际调用地址

3. 【验证】确认 ImGuiHudView 的 ivar 在 RootViewController 中的偏移
   - 分析 RootViewController 的 ivar layout
   - instanceSize=544, layout map: 0x02 0x1f 0x0f 0x0f 0x06 0x18 0x31

4. 【实施】推荐使用方案 D (最小改动)，只修改分支:
   - NOP 掉 isHUDEnabled 的检查分支
   - 强制 w2=1 传入 setHUDEnabled:
   - 保留所有原始 UI 设置代码

六、函数地址速查表
================================================================================

函数/选择器                    地址
────────────────────────────────────────
setHUDEnabled: selector        0x100373FE1
isHUDEnabled selector          0x1003739A3
tapMainButton: IMP            0x10009BB24
setHUDEnabled: (疑似) IMP      0x10001DD98
setupAndNotifyToggle IMP       0x100086288
RootViewController baseMethods 0x1000AC7E0 (61 methods)
ImGuiHudView baseMethods       0x1000AC160 (24 methods)
HUDRootViewController           0x1000AC448 (17 methods)
全局变量 [0x1003AE250]         被 setHUDEnabled: 读写
栈金丝雀全局 [0x1003A4150]     用于 setHUDEnabled: 的金丝雀
================================================================================
