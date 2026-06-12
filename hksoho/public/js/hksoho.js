// hksoho.js - 自訂 JS 用來修正 Frappe v15 + infintrix_theme 手機側邊欄問題

$(document).ready(function() {
    console.log('hksoho.js 已載入 - 使用 $(document).ready');

    // 強制移除 overflow-y: hidden 的函數
    function forceOverflowAuto() {
        document.documentElement.style.overflowY = 'auto';
        document.body.style.overflowY = 'auto';
        console.log('強制設 html/body overflow-y 為 auto');
    }

    // 立即執行一次
    forceOverflowAuto();

    // 每 300ms 檢查一次，持續 15 秒，防其他 JS 覆蓋
    let checkCount = 0;
    const overflowInterval = setInterval(function() {
        checkCount++;
        if (document.documentElement.style.overflowY !== 'auto' ||
            document.body.style.overflowY !== 'auto') {
            forceOverflowAuto();
            console.log('偵測到 overflow-y 被改，強制設回 auto');
        }
        if (checkCount >= 50) {
            clearInterval(overflowInterval);
            console.log('overflow-y 監控結束');
        }
    }, 300);

    // 延遲 1.5 秒再檢查手機模式與綁定（有些頁面 navbar 晚載入）
    setTimeout(function() {
        console.log('延遲檢查 - 目前視窗寬度：', window.innerWidth);

        if (window.innerWidth <= 767) {
            console.log('偵測到手機模式，開始綁定 sidebar toggle');

            // 主要 toggle 元素
            const toggleSelector = '.sidebar-toggle-placeholder';
            let toggles = document.querySelectorAll(toggleSelector);

            // 如果初次找不到，延遲 1 秒再找一次
            if (toggles.length === 0) {
                console.log('初次找不到 .sidebar-toggle-placeholder，延遲再找一次');
                setTimeout(() => {
                    toggles = document.querySelectorAll(toggleSelector);
                    bindToggleEvents(toggles);
                }, 1000);
            } else {
                bindToggleEvents(toggles);
            }

            function bindToggleEvents(toggles) {
                if (toggles.length > 0) {
                    console.log(`找到 sidebar-toggle-placeholder：${toggles.length} 個`);
                    toggles.forEach(toggle => {
                        toggle.addEventListener('click', function(e) {
                            e.preventDefault();
                            e.stopPropagation();
                            console.log('sidebar-toggle-placeholder 被點擊！');
                            toggleSidebar();
                        });
                    });
                } else {
                    console.log('延遲後還是找不到 .sidebar-toggle-placeholder');
                }
            }

            // 側邊欄展開/收合邏輯
            function toggleSidebar() {
                // 擴大搜尋範圍，找所有可能側邊欄元素
                let sidebar = document.querySelector(
                    '.sidebar, .desk-sidebar, .layout-sidebar, .side-section, ' +
                    '[class*="sidebar"], [class*="side"], [class*="menu"], ' +
                    '[class*="navigation"], [class*="drawer"], [class*="offcanvas"]'
                );

                if (sidebar) {
                    const isOpen = sidebar.classList.toggle('show');
                    document.body.classList.toggle('sidebar-open', isOpen);
                    console.log('找到側邊欄元素，class 名稱：', sidebar.className);
                    console.log('sidebar 已 toggle，狀態：', isOpen ? '展開' : '收合');
                } else {
                    console.log('擴大搜尋後還是找不到任何側邊欄相關元素');

                    // 輸出所有可能相關的元素供 debug
                    const possibleElements = document.querySelectorAll('[class*="side"], [class*="menu"], [class*="nav"], [class*="left"], [class*="drawer"]');
                    console.log('頁面中含有 side/menu/nav/left/drawer 的元素數量：', possibleElements.length);

                    if (possibleElements.length > 0) {
                        possibleElements.forEach((el, index) => {
                            console.log(`可能元素 ${index + 1} 的 class：`, el.className);
                            console.log(`元素 tag：`, el.tagName);
                            console.log(`元素 id：`, el.id || '無');
                        });
                    } else {
                        console.log('頁面中完全沒有 side/menu/nav 等相關 class 的元素');
                    }
                }
            }

            // 額外綁定 logo / navbar 點擊（預防主題使用 logo 當 toggle）
            const extraSelectors = ['.navbar-brand', '.logo', '.navbar-header', '.navbar .logo'];
            extraSelectors.forEach(sel => {
                document.querySelectorAll(sel).forEach(el => {
                    el.addEventListener('click', function(e) {
                        if (window.innerWidth <= 767) {
                            console.log(`點擊 ${sel}，嘗試展開 sidebar`);
                            toggleSidebar();
                        }
                    });
                });
            });

            // 點擊頁面其他地方關閉 sidebar
            document.addEventListener('click', function(e) {
                if (window.innerWidth <= 767) {
                    const sidebar = document.querySelector('.sidebar.show, .desk-sidebar.show, [class*="sidebar"].show');
                    const clickedToggle = e.target.closest('.sidebar-toggle-placeholder, .navbar-brand, .logo');
                    if (sidebar && !sidebar.contains(e.target) && !clickedToggle) {
                        sidebar.classList.remove('show');
                        document.body.classList.remove('sidebar-open');
                        console.log('點擊頁面外部，關閉 sidebar');
                    }
                }
            });
        } else {
            console.log('視窗寬度 > 767px，未啟用手機 sidebar 邏輯');
        }
    }, 1500);  // 延遲 1.5 秒，讓頁面資源載入完成
});