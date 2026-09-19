// LLM 额度桌面浮窗（原生 AppKit）+ 阈值预警 + 侧边自动隐藏
// 数据采集：执行 ~/.config/llm-board/ui.json 中 collector_cmd 指定的命令
//          （由 `llm-board setup` 生成，默认：采集一次并输出 JSON）
// 编译: swiftc -O -swift-version 5 src/ui/llm_monitor_desktop.swift -o bin/llm-monitor

import AppKit

// MARK: - 数据模型

struct Alert: Decodable {
    let level: String      // warn | crit
    let message: String
}

struct Row: Decodable {
    let key: String
    let label: String
    let sub: String?
    let value: String
    let frac: Double?
    let num: Double?
    let unit: String?
    let note: String?
    let alert: Alert?
}

struct Payload: Decodable {
    let source: String
    let rows: [Row]
}

// MARK: - 浮窗

final class MonitorCard: NSObject, NSApplicationDelegate, NSWindowDelegate {
    private var window: NSWindow!
    private var stack: NSStackView!
    private var stamp: NSTextField!
    private var titleLabel: NSTextField!
    private var timer: Timer?
    private var mouseMonitor: Any?
    private var mouseMovedMonitorLocal: Any?
    private var mouseUpMonitorLocal: Any?
    private var mouseUpMonitorGlobal: Any?
    private var mouseDownMonitorLocal: Any?
    private var mouseDownMonitorGlobal: Any?
    private var userDraggingPanel = false
    private var dragAnchor: NSPoint?
    private var pinnedScreenID: CGDirectDisplayID?
    private var collapseTimer: Timer?
    private var collapseGeneration = 0
    private var spinning = false
    private var pulsing = false
    private var root: NSStackView!                     // 内容根栈（展开态显示；收起态用 alpha 隐藏）
    private var lightsContainer: NSView!               // 收起态灯条容器（9pt 宽的把手只显示圆点）
    private var lightDots: [NSView] = []               // 每个数据源一个圆点，纵向对齐对应文字行
    private var lineViews: [NSView] = []               // 展开态每行视图，用来量「行的中心位置」

    // 侧边隐藏
    private var isExpanded = true
    private let edgeHandle: CGFloat = 9      // 收起后留在屏幕内的宽度（把手）
    private let edgeInset: CGFloat = 5       // 展开时离屏幕边缘的空隙
    private let revealZone: CGFloat = 16     // 鼠标进入边缘多少 pt 内触发滑出
    private let autoCollapseDelay: TimeInterval = 1.2

    private let width: CGFloat = 316
    private let uiConfigPath = NSString(string: "~/.config/llm-board/ui.json").expandingTildeInPath
    private var collectorCmd: [String] = []
    private var refreshInterval: TimeInterval = 300
    private let frameKey = "llmMonitorFrame"
    private let sideKey = "llmMonitorSide"
    private let screenKey = "llmMonitorScreen"
    private let alertKey = "llmMonitorAlertState"
    private let renotifyInterval: TimeInterval = 6 * 3600

    private let baseColor = NSColor(calibratedRed: 0.11, green: 0.11, blue: 0.13, alpha: 0.94)
    private let critColor = NSColor(calibratedRed: 0.34, green: 0.09, blue: 0.11, alpha: 0.96)

    func applicationDidFinishLaunching(_ note: Notification) {
        loadPinnedScreen()
        loadUIConfig()
        buildWindow()
        startMouseTracking()
        NotificationCenter.default.addObserver(self, selector: #selector(screensChanged),
                                               name: NSApplication.didChangeScreenParametersNotification,
                                               object: nil)
        refresh()
        timer = Timer.scheduledTimer(withTimeInterval: refreshInterval, repeats: true) { [weak self] _ in
            self?.refresh()
        }
    }

    /// 读取 ~/.config/llm-board/ui.json（由 `llm-board setup` 生成）：
    /// collector_cmd = 采集命令；refresh_interval_seconds = 刷新间隔。
    private func loadUIConfig() {
        guard let data = FileManager.default.contents(atPath: uiConfigPath),
              let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { return }
        if let cmd = obj["collector_cmd"] as? [String], !cmd.isEmpty {
            collectorCmd = cmd
        }
        if let iv = obj["refresh_interval_seconds"] as? Double, iv >= 30 {
            refreshInterval = iv
        }
    }

    func applicationWillTerminate(_ notification: Notification) {
        if let m = mouseMonitor { NSEvent.removeMonitor(m) }
        if let m = mouseMovedMonitorLocal { NSEvent.removeMonitor(m) }
        if let m = mouseUpMonitorLocal { NSEvent.removeMonitor(m) }
        if let m = mouseUpMonitorGlobal { NSEvent.removeMonitor(m) }
        if let m = mouseDownMonitorLocal { NSEvent.removeMonitor(m) }
        if let m = mouseDownMonitorGlobal { NSEvent.removeMonitor(m) }
        NotificationCenter.default.removeObserver(self)
        collapseTimer?.invalidate()
    }

    // MARK: 窗口

    // 小组件风格：连续曲率圆角 + 细描边 + 顶部高光
    // 半径随面板尺寸走：小组件(329x155)约 20pt ≈ 高度 13%，本面板 219pt 高 → 取 26
    private let cornerRadius: CGFloat = 26

    private func buildWindow() {
        window = NSWindow(contentRect: restoredFrame(),
                          styleMask: [.borderless],
                          backing: .buffered,
                          defer: false)
        window.level = .statusBar          // 抬高层级，避免被其他常驻窗口压住
        window.isOpaque = false
        // ❗窗口背景必须透明：底色要画在 contentView 的 layer 上，
        // 否则窗口的矩形背景会在圆角外侧露出一圈直角（压在浅色窗口上非常明显）
        window.backgroundColor = .clear
        window.hasShadow = true
        window.isMovableByWindowBackground = true
        // 接收本窗口上的 mouseMoved：本地监听（双挂）依赖它才能看到光标在面板上的移动
        window.acceptsMouseMovedEvents = true
        window.collectionBehavior = [.canJoinAllSpaces, .stationary, .fullScreenNone]
        window.delegate = self

        // 小组件风格：连续曲率圆角 + 细描边 + 顶部高光
        if let cv = window.contentView {
            cv.wantsLayer = true
            guard let layer = cv.layer else { return }
            layer.backgroundColor = baseColor.cgColor     // ← 底色跟着圆角一起裁
            layer.cornerRadius = self.cornerRadius
            layer.cornerCurve = .continuous        // ← 这是“小组件圆角”的关键
            layer.masksToBounds = true
            layer.borderWidth = 0.5
            layer.borderColor = NSColor(white: 1.0, alpha: 0.10).cgColor

            let gloss = CAGradientLayer()
            gloss.frame = cv.bounds
            gloss.autoresizingMask = [.layerWidthSizable, .layerHeightSizable]
            gloss.colors = [NSColor(white: 1.0, alpha: 0.06).cgColor,
                            NSColor(white: 1.0, alpha: 0.0).cgColor]
            gloss.startPoint = CGPoint(x: 0.5, y: 1.0)
            gloss.endPoint = CGPoint(x: 0.5, y: 0.42)
            layer.insertSublayer(gloss, at: 0)
        }

        root = NSStackView()
        root.orientation = .vertical
        root.alignment = .leading
        root.spacing = 8
        root.edgeInsets = NSEdgeInsets(top: 14, left: 16, bottom: 12, right: 16)
        root.translatesAutoresizingMaskIntoConstraints = false

        titleLabel = NSTextField(labelWithString: "额度看板")
        titleLabel.font = .systemFont(ofSize: 13, weight: .bold)
        titleLabel.textColor = .white

        stamp = NSTextField(labelWithString: "加载中…")
        stamp.font = .monospacedDigitSystemFont(ofSize: 10, weight: .regular)
        stamp.textColor = .tertiaryLabelColor

        let refreshBtn = NSButton(title: "⟳", target: self, action: #selector(refresh))
        refreshBtn.isBordered = false
        refreshBtn.font = .systemFont(ofSize: 14, weight: .semibold)
        refreshBtn.contentTintColor = .secondaryLabelColor
        refreshBtn.setButtonType(.momentaryChange)

        let closeBtn = NSButton(title: "✕", target: self, action: #selector(quit))
        closeBtn.isBordered = false
        closeBtn.font = .systemFont(ofSize: 12, weight: .semibold)
        closeBtn.contentTintColor = .secondaryLabelColor
        closeBtn.setButtonType(.momentaryChange)

        let header = NSStackView(views: [titleLabel, stamp, refreshBtn, closeBtn])
        header.orientation = .horizontal
        header.alignment = .centerY
        header.spacing = 8
        header.distribution = .fill

        stack = NSStackView()
        stack.orientation = .vertical
        stack.alignment = .leading
        stack.spacing = 10

        root.addArrangedSubview(header)
        root.addArrangedSubview(stack)

        window.contentView?.addSubview(root)
        if let cv = window.contentView {
            NSLayoutConstraint.activate([
                root.leadingAnchor.constraint(equalTo: cv.leadingAnchor),
                // 内容固定为整宽：收起态窗口缩到把手宽时，避免把内容压出负宽度约束告警
                root.widthAnchor.constraint(equalToConstant: width),
                root.topAnchor.constraint(equalTo: cv.topAnchor),
                root.bottomAnchor.constraint(equalTo: cv.bottomAnchor),
                header.widthAnchor.constraint(equalTo: root.widthAnchor, constant: -32),
            ])

            // ❗行内容的可用宽度也钉死（窗口宽 - 左右内边距）。不钉的话，超长 note /
            // 数据源标签会把整行顶到自然宽度，与固定宽度约束打架（表现为文字被硬裁、
            // 且行宽与栈宽不一致）。钉死后超长文本只在自己那一行内截断。
            stack.translatesAutoresizingMaskIntoConstraints = false
            stack.widthAnchor.constraint(equalToConstant: width - 32).isActive = true

            // 收起态的「灯条」：每条数据一个圆点，纵向落在该行原来的位置上。
            // ❗收起用 alpha 隐藏 root，而不是移出视图层级：render() 靠 cv.fittingSize
            // 自适应高度，内容一走 fittingSize 变 0，窗口高度会当场塌掉。
            lightsContainer = NSView()
            lightsContainer.translatesAutoresizingMaskIntoConstraints = false
            cv.addSubview(lightsContainer, positioned: .above, relativeTo: root)
            NSLayoutConstraint.activate([
                lightsContainer.centerXAnchor.constraint(equalTo: cv.centerXAnchor),
                lightsContainer.topAnchor.constraint(equalTo: cv.topAnchor),
                lightsContainer.bottomAnchor.constraint(equalTo: cv.bottomAnchor),
                lightsContainer.widthAnchor.constraint(equalToConstant: edgeHandle),
            ])
            lightsContainer.isHidden = true
        }
        window.orderFrontRegardless()
    }

    // MARK: 位置与侧边隐藏

    /// 显示器编号（NSScreenNumber 即 CGDirectDisplayID）
    private func displayID(of screen: NSScreen?) -> CGDirectDisplayID? {
        guard let s = screen,
              let n = s.deviceDescription[NSDeviceDescriptionKey("NSScreenNumber")] as? NSNumber else { return nil }
        return CGDirectDisplayID(n.uint32Value)
    }

    private func screen(withID id: CGDirectDisplayID) -> NSScreen? {
        NSScreen.screens.first { displayID(of: $0) == id }
    }

    private func loadPinnedScreen() {
        let saved = UserDefaults.standard.integer(forKey: screenKey)
        if saved > 0, screen(withID: CGDirectDisplayID(saved)) != nil {
            pinnedScreenID = CGDirectDisplayID(saved)
        }
    }

    private func pin(to screen: NSScreen) {
        guard let id = displayID(of: screen) else { return }
        pinnedScreenID = id
        UserDefaults.standard.set(Int(id), forKey: screenKey)
    }

    /// 参照屏解析：① 记忆的锚定屏 ② 窗口中心所在屏（并钉住） ③ 主屏兜底。
    /// ❗不能每帧用「窗口当前所在屏」当参照系：面板贴边时大半个身体压在相邻屏上，
    /// 会被判成「在邻屏」→ 面板自己弹到邻屏（实测踩过）。
    private func targetScreen() -> NSScreen? {
        if let id = pinnedScreenID, let s = screen(withID: id) { return s }
        if let w = window {
            let c = NSPoint(x: w.frame.midX, y: w.frame.midY)
            if let s = NSScreen.screens.first(where: { $0.frame.contains(c) }) {
                pin(to: s)
                return s
            }
        }
        return NSScreen.main ?? NSScreen.screens.first
    }

    private func screenBox() -> NSRect {
        targetScreen()?.visibleFrame ?? NSRect(x: 0, y: 0, width: 1440, height: 900)
    }

    /// 拖拽结束后的改绑：以「窗口中心」判定落在哪块屏（仅展开态调用；
    /// 收起态窗口只剩把手宽贴在屏边，极易绑到错误的屏）
    private func repinByWindowCenter() {
        let c = NSPoint(x: window.frame.midX, y: window.frame.midY)
        guard let s = NSScreen.screens.first(where: { $0.frame.contains(c) }) else { return }
        pin(to: s)
        UserDefaults.standard.set(dockSide(), forKey: sideKey)
    }

    // MARK: 几何调试（默认静默；LLM_BOARD_DEBUG=1 时向 stderr 打一行）

    private func debugState(_ tag: String) {
        guard ProcessInfo.processInfo.environment["LLM_BOARD_DEBUG"] == "1" else { return }
        let f = window.frame
        let id = pinnedScreenID.map { String(describing: $0) } ?? "-"
        let line = "[llm-board] \(tag) frame=\(Int(f.origin.x)),\(Int(f.origin.y)),\(Int(f.width))x\(Int(f.height))"
            + " expanded=\(isExpanded) movable=\(window.isMovableByWindowBackground) screen=\(id) side=\(dockSide())\n"
        FileHandle.standardError.write(Data(line.utf8))
    }

    /// 离哪边近就贴哪边（用户拖动后会自然切换）
    private func dockSide() -> String {
        let vf = screenBox()
        let f = window.frame
        return (f.minX - vf.minX) <= (vf.maxX - f.maxX) ? "left" : "right"
    }

    /// 展开：整宽贴边（留 edgeInset）；收起：缩到 edgeHandle 宽、留在锚定屏内
    /// （贴两屏接缝时也能正确隐藏与划出）。
    private func edgeFrame(expanded wantExpanded: Bool) -> NSRect {
        let vf = screenBox()
        var f = window.frame
        let left = dockSide() == "left"
        if wantExpanded {
            f.size.width = width
            f.origin.x = left ? vf.minX + edgeInset : vf.maxX - width - edgeInset
        } else {
            f.size.width = edgeHandle
            f.origin.x = left ? vf.minX : vf.maxX - edgeHandle
        }
        return f
    }

    /// 展开态显示文字内容，收起态只显示灯条（9pt 宽的把手塞文字只剩半截残字）。
    /// ❗收起用 alpha 隐藏 root，而不是移出视图层级：render() 靠 cv.fittingSize 算高度。
    private func setChrome(expanded: Bool) {
        root.alphaValue = expanded ? 1 : 0
        lightsContainer.isHidden = expanded
    }

    private func expand() {
        collapseTimer?.invalidate()
        guard !isExpanded else { return }
        isExpanded = true
        collapseGeneration += 1
        setChrome(expanded: true)
        window.isMovableByWindowBackground = true
        window.setFrame(edgeFrame(expanded: true), display: true, animate: true)
        window.orderFrontRegardless()          // 每次滑出都抬到最前，避免被别的窗口压住
        UserDefaults.standard.set(dockSide(), forKey: sideKey)
    }

    private func collapse() {
        guard isExpanded else { return }
        collapseTimer?.invalidate()
        isExpanded = false
        setChrome(expanded: false)
        window.isMovableByWindowBackground = false   // 收起时别被误拖
        window.setFrame(edgeFrame(expanded: false), display: true, animate: true)
    }

    private func scheduleCollapse(ignoreInside: Bool = false) {
        guard isExpanded else { return }
        collapseGeneration += 1
        let gen = collapseGeneration
        DispatchQueue.main.asyncAfter(deadline: .now() + autoCollapseDelay) { [weak self] in
            guard let self = self else { return }
            guard gen == self.collapseGeneration, self.isExpanded else { return }
            // 拖拽松手启动的收起（ignoreInside）不受「光标在面板上」豁免；但若用户
            // 又按下了鼠标（新一轮拖拽/点击进行中），本轮让位，由那次松手重新计时
            if ignoreInside && NSEvent.pressedMouseButtons != 0 { return }
            let inside = self.window.frame.insetBy(dx: -6, dy: -6).contains(NSEvent.mouseLocation)
            if ignoreInside || !inside { self.collapse() }
        }
    }

    /// 用户拖拽结束（松开鼠标）→ 吸附到锚定屏最近的边缘（支持多显示器）
    private func snapToNearestEdge(dragDistance: Double) {
        let vf = screenBox()
        var f = window.frame
        // 纵向：整块面板夹回屏内（不允许半出屏，防拖丢）
        f.origin.y = min(max(f.origin.y, vf.minY + 4), vf.maxY - f.height - 4)
        // 横向：按窗口中心就近选左/右边缘
        let side = (f.midX - vf.minX) <= (vf.maxX - f.midX) ? "left" : "right"
        UserDefaults.standard.set(side, forKey: sideKey)
        f.size.width = width
        f.origin.x = (side == "left") ? vf.minX + edgeInset : vf.maxX - width - edgeInset
        isExpanded = true
        collapseTimer?.invalidate()
        collapseGeneration += 1
        window.isMovableByWindowBackground = true
        window.setFrame(f, display: true, animate: true)
        window.orderFrontRegardless()
        debugState("吸附(拖拽 \(Int(dragDistance))pt → \(side)侧)")
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) { [weak self] in
            self?.saveFrame()
        }
    }

    /// 松开鼠标：先按窗口中心改绑（仅展开态）；位移 ≥8pt 才吸附；
    /// 微动/点按钮只改绑、不把面板弹走。
    private func handleDragEnd() {
        guard userDraggingPanel || dragAnchor != nil else { return }
        let anchor = dragAnchor
        let origin = window.frame.origin
        let moved = anchor.map { hypot(Double(origin.x - $0.x), Double(origin.y - $0.y)) } ?? 0
        defer {
            dragAnchor = nil
            userDraggingPanel = false
        }
        if isExpanded { repinByWindowCenter() }
        guard moved >= 8 else {
            debugState("拖拽结束（位移 \(Int(moved))pt <8，未吸附）")
            return
        }
        snapToNearestEdge(dragDistance: moved)
        // 松手即启动收起计时（清单⑤）：拖完 ~autoCollapseDelay 后自动收起，
        // 不再要求「先把鼠标移出面板」；若延时内又开始拖拽则本轮让位。
        scheduleCollapse(ignoreInside: true)
    }

    // MARK: NSWindowDelegate

    /// 只记录「按住鼠标产生的窗口移动」= 用户拖拽；程序化动画（收起/滑出）不计入
    func windowDidMove(_ notification: Notification) {
        guard NSEvent.pressedMouseButtons != 0 else { return }
        if dragAnchor == nil { dragAnchor = window.frame.origin }
        if let a = dragAnchor,
           hypot(Double(window.frame.origin.x - a.x), Double(window.frame.origin.y - a.y)) >= 8 {
            userDraggingPanel = true
        }
    }

    private func startMouseTracking() {
        // 全局鼠标移动监听：mouseMoved 不需要辅助功能权限（只收「别的应用」上空的移动）
        mouseMonitor = NSEvent.addGlobalMonitorForEvents(matching: [.mouseMoved]) { [weak self] _ in
            self?.onMouseMoved()
        }
        // 本地 mouseMoved 监听（双挂，清单⑤）：global monitor 收不到本应用自身的事件，
        // 光标在面板上移动时只有本地监听能收到。
        // ⚠️ 闭包必须返回 event 放行；返回 nil 会吞掉本应用全部鼠标移动事件。
        mouseMovedMonitorLocal = NSEvent.addLocalMonitorForEvents(matching: [.mouseMoved]) { [weak self] event in
            self?.onMouseMoved()
            return event
        }
        // 拖拽起点：按下落在面板内 → 置位 + 记 anchor。
        // （本应用内的事件 global monitor 收不到 → 本地 + 全局双挂）
        mouseDownMonitorLocal = NSEvent.addLocalMonitorForEvents(matching: [.leftMouseDown]) { [weak self] event in
            self?.beginPotentialDrag(at: NSEvent.mouseLocation)
            return event
        }
        mouseDownMonitorGlobal = NSEvent.addGlobalMonitorForEvents(matching: [.leftMouseDown]) { [weak self] _ in
            self?.beginPotentialDrag(at: NSEvent.mouseLocation)
        }
        // 松开鼠标：本地 + 全局双挂（自己窗口内的松开 global monitor 收不到）→ handleDragEnd
        mouseUpMonitorLocal = NSEvent.addLocalMonitorForEvents(matching: [.leftMouseUp]) { [weak self] event in
            self?.handleDragEnd()
            return event
        }
        mouseUpMonitorGlobal = NSEvent.addGlobalMonitorForEvents(matching: [.leftMouseUp]) { [weak self] _ in
            self?.handleDragEnd()
        }
    }

    private func beginPotentialDrag(at point: NSPoint) {
        guard window.frame.contains(point) else { return }
        userDraggingPanel = true
        dragAnchor = window.frame.origin
    }

    private func onMouseMoved() {
        guard NSEvent.pressedMouseButtons == 0 else { return }   // 拖拽窗口/选择时不动
        let m = NSEvent.mouseLocation
        let vf = screenBox()
        let f = window.frame

        if isExpanded {
            if f.insetBy(dx: -8, dy: -8).contains(m) {
                collapseTimer?.invalidate()
            } else {
                scheduleCollapse()
            }
        } else {
            let leftDock = dockSide() == "left"
            let nearEdge = leftDock ? (m.x <= vf.minX + revealZone) : (m.x >= vf.maxX - revealZone)
            let nearY = abs(m.y - f.midY) <= max(f.height, 220) / 2
            // 划出只认「边缘带」（±revealZone）：面板贴在两屏分界上时，从邻屏一侧
            // 靠到边界也能划出；鼠标深入邻屏则不误触发
            let withinEdgeBand = leftDock ? (m.x >= vf.minX - revealZone) : (m.x <= vf.maxX + revealZone)
            if nearEdge && nearY && withinEdgeBand { expand() }
        }
    }

    // MARK: 显示器插拔 / 排列变化

    @objc private func screensChanged() {
        if let id = pinnedScreenID, screen(withID: id) == nil { pinnedScreenID = nil }
        if isExpanded { repinByWindowCenter() }
        window.setFrame(edgeFrame(expanded: isExpanded), display: true)
        debugState("屏参数变化")
    }

    private func restoredFrame() -> NSRect {
        // 多显示器：优先恢复到记忆的锚定屏（此时尚无窗口，「窗口所在屏」不可查）
        let anchorScreen = pinnedScreenID.flatMap { screen(withID: $0) } ?? NSScreen.main ?? NSScreen.screens.first
        let vf = anchorScreen?.visibleFrame ?? NSRect(x: 0, y: 0, width: 1440, height: 900)
        var f: NSRect
        var side = UserDefaults.standard.string(forKey: sideKey)
        if let saved = UserDefaults.standard.string(forKey: frameKey) {
            let parts = saved.split(separator: ",").compactMap { Double($0) }
            if parts.count == 4 {
                f = NSRect(x: parts[0], y: parts[1], width: width, height: max(parts[3], 120))
                if side == nil {                       // 首次升级：按上次所在位置推断贴哪边
                    side = parts[0] < vf.midX ? "left" : "right"
                }
                // 保证整块仍在锚定屏可见范围内
                f.origin.y = min(max(f.origin.y, vf.minY + 4), vf.maxY - f.height - 4)
            } else {
                f = NSRect(x: vf.minX + edgeInset, y: vf.minY + 120, width: width, height: 200)
            }
        } else {
            f = NSRect(x: vf.maxX - width - edgeInset, y: vf.maxY - 210, width: width, height: 200)
        }
        f.size.width = width
        let s = side ?? "right"
        f.origin.x = s == "left" ? vf.minX + edgeInset : vf.maxX - width - edgeInset
        return f
    }

    private func saveFrame() {
        let f = window.frame
        UserDefaults.standard.set("\(f.origin.x),\(f.origin.y),\(f.size.width),\(f.size.height)", forKey: frameKey)
        UserDefaults.standard.set(dockSide(), forKey: sideKey)
        if let id = pinnedScreenID {
            UserDefaults.standard.set(Int(id), forKey: screenKey)
        }
    }

    // MARK: 采集

    @objc private func refresh() {
        guard !spinning else { return }
        spinning = true
        stamp.stringValue = "更新中…"
        DispatchQueue.global(qos: .utility).async { [weak self] in
            let payload = self?.runCollector()
            DispatchQueue.main.async {
                self?.spinning = false
                self?.render(payload)
            }
        }
    }

    private func runCollector() -> Payload? {
        guard let exe = collectorCmd.first else { return nil }
        let p = Process()
        p.executableURL = URL(fileURLWithPath: exe)
        p.arguments = Array(collectorCmd.dropFirst())
        let out = Pipe()
        p.standardOutput = out
        p.standardError = Pipe()
        do { try p.run() } catch { return nil }
        let data = out.fileHandleForReading.readDataToEndOfFile()
        p.waitUntilExit()
        return try? JSONDecoder().decode(Payload.self, from: data)
    }

    // MARK: 预警

    private func storedAlerts() -> [String: [String: Any]] {
        (UserDefaults.standard.dictionary(forKey: alertKey) as? [String: [String: Any]]) ?? [:]
    }

    private func notify(_ message: String) {
        // 1) 声音（无需任何权限，最可靠）
        NSSound(named: "Ping")?.play()

        // 2) 通知：terminal-notifier 优先（有独立签名），osascript 兜底
        let paths = ["/opt/homebrew/bin/terminal-notifier", "/usr/local/bin/terminal-notifier"]
        if let tn = paths.first(where: { FileManager.default.isExecutableFile(atPath: $0) }) {
            let p = Process()
            p.executableURL = URL(fileURLWithPath: tn)
            p.arguments = ["-title", "额度预警", "-message", message, "-sound", "Ping"]
            try? p.run()
        } else {
            let p = Process()
            p.executableURL = URL(fileURLWithPath: "/usr/bin/osascript")
            p.arguments = ["-e", "display notification \"\(message)\" with title \"额度预警\""]
            try? p.run()
        }

        // 3) 落盘一份告警日志，事后可追溯
        let logPath = NSString(string: "~/.config/llm-board/alerts.log").expandingTildeInPath
        let dir = (logPath as NSString).deletingLastPathComponent
        try? FileManager.default.createDirectory(atPath: dir, withIntermediateDirectories: true)
        let df = DateFormatter()
        df.dateFormat = "yyyy-MM-dd HH:mm:ss"
        let line = "[\(df.string(from: Date()))] \(message)\n"
        if let fh = FileHandle(forWritingAtPath: logPath) {
            fh.seekToEndOfFile()
            fh.write(line.data(using: .utf8)!)
            try? fh.close()
        } else {
            try? line.write(toFile: logPath, atomically: true, encoding: .utf8)
        }
    }

    /// 只在「等级变化」或「距上次同类告警 > 6h」时提醒，避免每 5 分钟刷屏
    private func handleAlerts(_ rows: [Row]) -> String? {
        var store = storedAlerts()
        var worst: String?
        let now = Date().timeIntervalSince1970

        for r in rows {
            let level = r.alert?.level
            let prev = store[r.key]
            let prevLevel = prev?["level"] as? String
            let prevAt = prev?["at"] as? Double ?? 0

            if let level = level, let msg = r.alert?.message {
                if worst != "crit" { worst = level }
                let escalated = prevLevel != level
                let stale = now - prevAt > renotifyInterval
                if escalated || stale {
                    notify(msg)
                    store[r.key] = ["level": level, "at": now]
                }
            } else if prevLevel != nil {
                store.removeValue(forKey: r.key)   // 恢复正常，清掉状态
            }
        }
        UserDefaults.standard.set(store, forKey: alertKey)
        return worst
    }

    private func setCardColor(_ c: NSColor) {
        window.contentView?.layer?.backgroundColor = c.cgColor
    }

    private func pulse(times: Int) {
        guard !pulsing else { return }
        pulsing = true
        var n = 0
        let t = Timer(timeInterval: 0.45, repeats: true) { [weak self] timer in
            guard let self = self else { timer.invalidate(); return }
            n += 1
            self.setCardColor((n % 2 == 1) ? self.critColor : self.baseColor)
            if n >= times * 2 {
                timer.invalidate()
                self.setCardColor(self.critColor)
                self.pulsing = false
            }
        }
        RunLoop.main.add(t, forMode: .common)
    }

    // MARK: 渲染

    private func tone(_ r: Row) -> NSColor {
        if r.alert?.level == "crit" { return .systemRed }
        if r.alert?.level == "warn" { return .systemOrange }
        guard let f = r.frac else { return .white }
        if f > 0.5 { return .systemGreen }
        if f > 0.2 { return .systemYellow }
        return .systemRed
    }

    /// 收起态圆灯专用配色（与展开态文字色分开）：
    /// 百分比型（Codex）按剩余比例分档；余额型没有 frac，只能靠告警等级 ——
    /// 未触发告警 = 「够用」→ 绿。灯的全部意义是「一眼看出有没有事」，
    /// 余额行给白色在这里等于没有信息。
    private func lightColor(_ r: Row) -> NSColor {
        if r.alert?.level == "crit" { return .systemRed }
        if r.alert?.level == "warn" { return .systemYellow }
        if let f = r.frac { return f > 0.5 ? .systemGreen : (f > 0.2 ? .systemYellow : .systemRed) }
        return .systemGreen
    }

    /// 单行文本一律「单行 + 尾部省略号 + 可压缩」：压缩阻力降到 low 是配合钉死的
    /// 行宽用的，否则 label 的 intrinsic 宽度会跟固定宽度打架（表现为文字被硬裁）。
    private func fitLabel(_ f: NSTextField, compressible: Bool = true) {
        f.usesSingleLineMode = true
        f.lineBreakMode = .byTruncatingTail
        if compressible {
            f.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
        }
    }

    /// 收起态灯条：每个圆点的纵向位置 = 展开态对应那一行的中心（render 里量好传进来）。
    /// 位置本身也携带信息：哪一行、行高多少、行间距多大，与展开态完全一致。
    private func rebuildLights(offsets: [CGFloat], colors: [NSColor]) {
        for v in lightDots { v.removeFromSuperview() }
        lightDots.removeAll()
        for (i, dy) in offsets.enumerated() where i < colors.count {
            let dot = NSView()
            dot.wantsLayer = true
            dot.layer?.cornerRadius = 2.5
            dot.layer?.backgroundColor = colors[i].cgColor
            dot.translatesAutoresizingMaskIntoConstraints = false
            lightsContainer.addSubview(dot)             // ❗先入父视图再激活约束，否则「无共同祖先」抛异常
            NSLayoutConstraint.activate([
                dot.widthAnchor.constraint(equalToConstant: 5),
                dot.heightAnchor.constraint(equalToConstant: 5),
                dot.centerXAnchor.constraint(equalTo: lightsContainer.centerXAnchor),
                dot.centerYAnchor.constraint(equalTo: lightsContainer.topAnchor, constant: dy),
            ])
            lightDots.append(dot)
        }
    }

    private func render(_ payload: Payload?) {
        for v in stack.arrangedSubviews { stack.removeArrangedSubview(v); v.removeFromSuperview() }
        lineViews.removeAll()

        let df = DateFormatter()
        df.dateFormat = "HH:mm"
        let rows = payload?.rows ?? []
        stamp.stringValue = rows.isEmpty ? "取数失败" : df.string(from: Date())
        titleLabel.stringValue = "额度看板"

        for r in rows {
            if r.alert?.level == "crit", titleLabel.stringValue == "额度看板" {
                titleLabel.stringValue = "⚠️ 额度看板"
            }
        }
        setCardColor(baseColor)

        for r in rows {
            let title = NSTextField(labelWithString: r.sub.map { "\(r.label) · \($0)" } ?? r.label)
            title.font = .systemFont(ofSize: 12.5, weight: .semibold)
            title.textColor = tone(r)
            fitLabel(title)

            let value = NSTextField(labelWithString: r.value)
            value.font = .monospacedDigitSystemFont(ofSize: 15, weight: .bold)
            value.textColor = tone(r)
            value.alignment = .right
            fitLabel(value, compressible: false)        // 数值优先保完整

            let left = NSStackView()
            left.orientation = .vertical
            left.alignment = .leading
            left.spacing = 1
            left.addArrangedSubview(title)
            let note = (r.alert?.level == "crit" || r.alert?.level == "warn")
                ? (r.alert?.message ?? r.note ?? "")
                : (r.note ?? "")
            if !note.isEmpty {
                let n = NSTextField(labelWithString: note)
                n.font = .systemFont(ofSize: 10)
                n.textColor = (r.alert != nil) ? tone(r) : .secondaryLabelColor
                fitLabel(n)
                left.addArrangedSubview(n)
            }

            let line = NSStackView(views: [left, value])
            line.orientation = .horizontal
            line.alignment = .top
            line.spacing = 10
            line.distribution = .fill
            left.setContentHuggingPriority(.defaultLow, for: .horizontal)
            value.setContentHuggingPriority(.defaultHigh, for: .horizontal)
            stack.addArrangedSubview(line)
            line.widthAnchor.constraint(equalTo: stack.widthAnchor).isActive = true
            lineViews.append(line)
        }

        if rows.isEmpty {
            let msg = collectorCmd.isEmpty
                ? "未配置采集器：先运行 `llm-board setup` 生成 ui.json"
                : "取数失败（代理 / 网络？）"
            let err = NSTextField(labelWithString: msg)
            err.font = .systemFont(ofSize: 11)
            err.textColor = .secondaryLabelColor
            fitLabel(err)
            stack.addArrangedSubview(err)
        } else {
            let mins = max(1, Int(refreshInterval / 60))
            let foot = NSTextField(labelWithString: "数据源 \(payload?.source ?? "?") · \(mins) 分钟自刷 · 移到屏幕边缘展开")
            foot.font = .systemFont(ofSize: 9.5)
            foot.textColor = .tertiaryLabelColor
            fitLabel(foot)
            stack.addArrangedSubview(foot)
            // 脚注在 .leading 对齐的 stack 里不会被自动收窄 → 单独限宽走省略号（约束须在入栈后激活）
            foot.widthAnchor.constraint(lessThanOrEqualTo: stack.widthAnchor).isActive = true
        }

        let worst = handleAlerts(rows)
        if worst == "crit" {
            setCardColor(critColor)
            pulse(times: 2)
        }

        // 高度自适应，顶部锚定 + 贴边（保持展开/收起状态）
        window.layoutIfNeeded()
        let fit = window.contentView?.fittingSize ?? NSSize(width: width, height: 200)
        var f = window.frame
        let top = f.maxY
        f.size = NSSize(width: width, height: max(fit.height, 120))
        f.origin.y = min(top - f.size.height, screenBox().maxY - f.size.height - 4)
        window.setFrame(f, display: true)
        window.setFrame(edgeFrame(expanded: isExpanded), display: true)

        // 量出每行中心（以内容区顶部为基准）→ 收起态的圆点就落在这些位置上。
        // 两种宽度下内容都按固定宽度布局，所以这里量到的位置在收起态同样成立。
        if let cv = window.contentView {
            window.layoutIfNeeded()
            let h = cv.bounds.height
            let offsets = lineViews.map { h - $0.convert($0.bounds, to: cv).midY }
            let colors = rows.map { lightColor($0) }
            if offsets.isEmpty {
                rebuildLights(offsets: [44], colors: [.systemGray])   // 取数失败：留一个灰点占位
            } else {
                rebuildLights(offsets: offsets, colors: colors)
            }
        }
        saveFrame()
    }

    @objc private func quit() {
        saveFrame()
        NSApp.terminate(nil)
    }
}

let app = NSApplication.shared
app.setActivationPolicy(.accessory)
let controller = MonitorCard()
app.delegate = controller
app.run()
