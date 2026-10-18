/* WMU 课表 - 交互逻辑
 * 数据来源优先级：
 *   1. window.SCHEDULE_DATA（由 Python 侧注入，或本地静态 JSON）
 *   2. fetch('schedule-data.json')
 *   3. 无数据 → 空态提示
 */

(function () {
  'use strict';

  var DAY_NAMES = ['', '周一', '周二', '周三', '周四', '周五', '周六', '周日'];
  var MONTH_NAMES = ['', '一月', '二月', '三月', '四月', '五月', '六月',
    '七月', '八月', '九月', '十月', '十一月', '十二月'];

  var currentWeek = 1;
  var data = null;

  var $ = function (id) { return document.getElementById(id); };

  // ---------------- 数据加载 ----------------
  // 优先级：原生桥（APK 内）> window.SCHEDULE_DATA > fetch 本地文件（桌面预览）
  function loadData(cb) {
    if (window.SCHEDULE_DATA) { cb(window.SCHEDULE_DATA); return; }
    if (window.AndroidSchedule && window.AndroidSchedule.readSchedule) {
      try {
        var raw = window.AndroidSchedule.readSchedule();
        if (raw) { cb(JSON.parse(raw)); return; }
      } catch (e) { /* 落退 fetch */ }
    }
    fetch('schedule-data.json')
      .then(function (r) { if (!r.ok) throw new Error('no data'); return r.json(); })
      .then(cb)
      .catch(function () { showEmpty(); });
  }

  function showEmpty() {
    $('schedule').innerHTML = '';
    $('month-list').innerHTML = '';
    var strip = $('today-strip');
    if (strip) strip.classList.add('hidden');
    $('week-label').textContent = '暂无课表';
    var sl = $('student-label');
    if (sl) sl.textContent = '';
    var tip = $('empty-tip');
    var native = !!(window.AndroidSchedule && window.AndroidSchedule.startLogin);
    tip.innerHTML = native
      ? '还没有课表数据<br><button class="login-btn" id="btn-login-start">登录教务系统</button>'
      : '本地暂无课表数据。<br>请先在电脑上运行 <code>python main.py --year 2026 --term 1</code> 拉取。';
    tip.classList.remove('hidden');
    var btn = $('btn-login-start');
    if (btn) {
      btn.onclick = function () {
        btn.disabled = true;
        btn.textContent = '正在打开登录…';
        window.AndroidSchedule.startLogin();
      };
    }
  }

  /* 原生事件回调：拉取中提示 / 完成刷新 / 失败 */
  window.__onNativeEvent = function (message) {
    if (message === null || message === undefined) {
      loadData(function (d) {
        data = d; currentWeek = startWeek(); render();
        var tip = $('empty-tip');
        if (tip) tip.classList.add('hidden');
      });
      return;
    }
    // 已有课表时提示走原生 Toast，不掀空态层挡界面
    if (data) return;
    var tip = $('empty-tip');
    if (tip) {
      tip.classList.remove('hidden');
      tip.innerHTML = '<span class="login-msg">' + esc(message) + '</span>';
    }
  };

  // ---------------- 渲染 ----------------
  function render() {
    if (!data) return;
    renderSidebar();
    renderWeek(currentWeek);
    updateFabToday();
  }

  /* 打开 APP 时定位到哪一周：优先 today.today_week（按当天日期实时算），
   * 学期外（寒暑假）退回拉取时的 current_week，再兜底第 1 周 */
  function startWeek() {
    var t = data ? (data.today || {}) : {};
    if (t.in_term && t.today_week) return t.today_week;
    return (data && data.current_week) || 1;
  }

  function renderSidebar() {
    var box = $('month-list');
    box.innerHTML = '';

    // 按周一的月份分组（week_months 由 Python 按 term_start 算好）
    var byMonth = {};
    for (var w = 1; w <= data.total_weeks; w++) {
      var m = data.week_months ? data.week_months[String(w)] : 0;
      if (!m) continue;
      if (!byMonth[m]) byMonth[m] = [];
      byMonth[m].push(w);
    }
    var months = Object.keys(byMonth).map(Number).sort(function (a, b) { return a - b; });

    // 当前周所在月份默认展开
    var currentMonth = data.week_months ? data.week_months[String(currentWeek)] : 0;

    // “本周”用实时计算的 today_week（拉取时的 current_week 会随日期漂移）
    var thisWeek = (data.today && data.today.in_term) ? data.today.today_week : 0;

    months.forEach(function (m) {
      var item = document.createElement('div');
      item.className = 'month-item' + (m === currentMonth ? ' open' : '');
      item.dataset.month = m;

      var hasCurrent = thisWeek > 0 && byMonth[m].indexOf(thisWeek) !== -1;
      var btn = document.createElement('button');
      btn.className = 'month-btn' + (hasCurrent ? ' current' : '');
      btn.innerHTML = '<span>' + MONTH_NAMES[m] + '</span><span class="arrow">›</span>';
      btn.onclick = function () { item.classList.toggle('open'); };

      var list = document.createElement('div');
      list.className = 'week-list';
      byMonth[m].forEach(function (w) {
        var wk = document.createElement('button');
        wk.className = 'week-item' + (w === currentWeek ? ' active' : '') +
          (w === thisWeek ? ' current' : '');
        var date = data.week_dates ? data.week_dates[String(w)] : '';
        wk.innerHTML = '第' + w + '周' + (date ? ' <small>' + date + '</small>' : '');
        wk.dataset.week = w;
        wk.onclick = function () {
          var w = +this.dataset.week;
          closeDrawer();
          if (w === currentWeek) return;
          // 与手势切周同款方向缓动
          switchWeek(w > currentWeek ? 'next' : 'prev', w);
        };
        list.appendChild(wk);
      });

      item.appendChild(btn);
      item.appendChild(list);
      box.appendChild(item);
    });
  }

  function renderWeek(week) {
    var box = $('schedule');
    box.innerHTML = '';

    var date = data.week_dates ? data.week_dates[String(week)] : '';
    var t0 = data.today || {};
    var thisWeek = t0.in_term ? t0.today_week : 0;
    var tag = week === thisWeek ? '本周' : '第 ' + week + ' 周';
    $('week-label').textContent = tag + (date ? '（' + date + ' 起）' : '');
    $('student-label').textContent =
      (data.student.name || '') + (data.student.class_name ? ' · ' + data.student.class_name : '');

    renderTodayStrip(week);

    var days = data.weeks[String(week)] || {};
    for (var d = 1; d <= 7; d++) {
      var list = days[String(d)] || [];
      var block = document.createElement('section');
      block.className = 'day-block';

      var head = document.createElement('div');
      head.className = 'day-head';
      head.innerHTML = '<span class="day-name">' + DAY_NAMES[d] + '</span>' +
        '<span class="day-count">' + (list.length ? list.length + ' 门课' : '无课') + '</span>';
      block.appendChild(head);

      list.forEach(function (c) { block.appendChild(courseCard(c)); });
      box.appendChild(block);
    }

    // 选修课（无固定上课时间）：独立区块放最后
    var electives = days['0'] || [];
    if (electives.length) {
      var eb = document.createElement('section');
      eb.className = 'day-block';
      var eh = document.createElement('div');
      eh.className = 'day-head';
      eh.innerHTML = '<span class="day-name elective">选修课</span>' +
        '<span class="day-count">' + electives.length + ' 门</span>';
      eb.appendChild(eh);
      electives.forEach(function (c) { eb.appendChild(courseCard(c)); });
      box.appendChild(eb);
    }
  }

  /* 当日课程胶囊：只看本周时显示，点胶囊进当日时间轴 */
  function renderTodayStrip(week) {
    var strip = $('today-strip');
    strip.innerHTML = '';
    var today = data.today || {};
    var isThisWeek = today.in_term && today.today_week === week;
    if (!isThisWeek) {
      strip.classList.add('hidden');
      return;
    }
    strip.classList.remove('hidden');

    var hint = document.createElement('span');
    hint.className = 'strip-hint';
    /* today_weekday 值域 1~7（1=周一 … 7=周日，Java Calendar 公式换算来的） */
    hint.textContent = '今天 周' +
      (['一', '二', '三', '四', '五', '六', '日'][today.today_weekday - 1] || '') + '：';
    strip.appendChild(hint);

    var days = data.weeks[String(week)] || {};
    var list = (days[String(today.today_weekday)] || []).concat(days['0'] || []);
    if (!list.length) {
      var free = document.createElement('span');
      free.className = 'pill free';
      free.textContent = '今天没课';
      strip.appendChild(free);
      return;
    }
    list.forEach(function (c, i) {
      var pill = document.createElement('button');
      pill.className = 'pill' + (c.is_elective ? ' elective' : '');
      pill.style.animationDelay = (i * 40) + 'ms';
      pill.innerHTML = '<span class="pill-sec">' + esc(c.sections || '选修') + '</span>' +
        '<span>' + esc(c.title) + '</span>';
      pill.onclick = function () { openDayView(week, today.today_weekday); };
      strip.appendChild(pill);
    });
  }

  /* 当日详情页：纵轴按节次号定位（横轴=第N节），仿钉钉但单列铺开 */
  var SECTION_ROW_H = 52;   // 每节课的纵轴高度(px)

  function openDayView(week, weekday) {
    var body = $('day-body');
    body.innerHTML = '';

    var dateStr = data.week_dates ? data.week_dates[String(week)] : '';
    var monday = null;
    if (dateStr) {
      var parts = dateStr.split('-');
      monday = { m: +parts[0], d: +parts[1] };
    }
    var dayNum = monday ? monday.d + (weekday - 1) : null;
    /* weekday 值域 1~7（1=周一 … 7=周日） */
    $('day-heading').textContent = '周' + (['一', '二', '三', '四', '五', '六', '日'][weekday - 1] || '') +
      (dayNum ? ' ' + monday.m + '月' + dayNum + '日' : '');
    $('day-sub').textContent = '第 ' + week + ' 周' +
      (monday ? ' · ' + monday.m + '月' + dayNum + '日' : '');

    var days = data.weeks[String(week)] || {};
    var timed = (days[String(weekday)] || []).slice().sort(function (a, b) {
      return (a.section_start || 0) - (b.section_start || 0);
    });
    var electives = days['0'] || [];

    if (!timed.length && !electives.length) {
      body.innerHTML = '<div class="tl-empty">这一天没有课</div>';
      showDayView();
      return;
    }

    // 纵轴范围：从当周最早节到最晚节，前后各留 1 节余量
    var minSec = 99, maxSec = 1;
    timed.forEach(function (c) {
      if (c.section_start) minSec = Math.min(minSec, c.section_start);
      if (c.section_end) maxSec = Math.max(maxSec, c.section_end);
    });
    if (!timed.length) { minSec = 1; maxSec = 12; }
    minSec = Math.max(1, minSec - 1);
    maxSec = maxSec + 1;

    var axisH = (maxSec - minSec + 1) * SECTION_ROW_H;

    // 纵轴刻度（每节一行，标注节次号 + 起止时间）
    var axis = document.createElement('div');
    axis.className = 'tl-axis';
    axis.style.height = axisH + 'px';
    for (var s = minSec; s <= maxSec; s++) {
      var tick = document.createElement('div');
      tick.className = 'tl-tick';
      tick.style.top = ((s - minSec) * SECTION_ROW_H) + 'px';
      var rng = sectionTimeRange(s);
      tick.innerHTML = '<b>第' + s + '节</b>' + (rng ? '<i>' + rng + '</i>' : '');
      axis.appendChild(tick);
    }

    // 课程块：按节次号绝对定位，高度=跨越节数
    var track = document.createElement('div');
    track.className = 'tl-track';
    track.style.height = axisH + 'px';
    var idx = 0;
    timed.forEach(function (c) {
      var row = document.createElement('button');
      var from = c.section_start || minSec;
      var to = c.section_end || from;
      row.className = 'tl-block' + (c.is_elective ? ' elective' : '');
      row.style.top = ((from - minSec) * SECTION_ROW_H) + 'px';
      row.style.height = ((to - from + 1) * SECTION_ROW_H - 8) + 'px';
      row.style.animationDelay = (idx * 50) + 'ms';
      idx++;
      row.innerHTML =
        '<div class="c-name">' + esc(c.title) + '</div>' +
        '<div class="c-meta">' +
        '<span>' + esc(c.sections || '') + '</span>' +
        '<span>' + esc(c.place || '地点待定') + '</span>' +
        '<span>' + esc(c.teacher || '教师待定') + '</span>' +
        '</div>';
      row.onclick = function () { showDetail(c); };
      track.appendChild(row);
    });

    var wrap = document.createElement('div');
    wrap.className = 'tl-wrap';
    wrap.appendChild(axis);
    wrap.appendChild(track);
    body.appendChild(wrap);

    // 选修课（无节次）：纵轴下方单独列出
    if (electives.length) {
      var eb = document.createElement('div');
      eb.className = 'tl-elective';
      var eh = document.createElement('div');
      eh.className = 'tl-elective-head';
      eh.textContent = '选修课（无固定上课时间）';
      eb.appendChild(eh);
      electives.forEach(function (c, i) {
        var card = document.createElement('button');
        card.className = 'tl-block elective static';
        card.style.animationDelay = ((timed.length + i) * 50) + 'ms';
        card.innerHTML =
          '<div class="c-name">' + esc(c.title) + '</div>' +
          '<div class="c-meta">' +
          '<span>' + esc(c.weeks_raw || '选修') + '</span>' +
          '<span>' + esc(c.place || '网络课程') + '</span>' +
          '<span>' + esc(c.teacher || '教师待定') + '</span>' +
          '</div>';
        card.onclick = function () { showDetail(c); };
        eb.appendChild(card);
      });
      body.appendChild(eb);
    }

    showDayView();
  }

  /* 某节的上课时间：直接用 Python 注入的校历节次表（不反查课程） */
  function sectionTimeRange(sec) {
    var tables = data.section_tables || {};
    // 当日页的纵轴用茶山表（默认）；滨海校区课程的时间已在卡片 time_text 里
    var t = tables['default'] || {};
    var hm = t[String(sec)];
    return hm || '';
  }

  function showDayView() {
    var dv = $('day-view');
    dv.classList.remove('hidden', 'closing');
  }

  function closeDayView() {
    var dv = $('day-view');
    dv.classList.add('closing');
    setTimeout(function () { dv.classList.add('hidden'); dv.classList.remove('closing'); }, 300);
  }

  function courseCard(c) {
    var el = document.createElement('button');
    el.className = 'course-card' + (c.is_elective ? ' elective' : '');
    var badge = c.is_elective ? '<span class="badge">选修课</span>' : '';
    el.innerHTML =
      '<div class="c-name">' + esc(c.title) + badge + '</div>' +
      '<div class="c-meta">' +
      '<span>' + esc(sectionLabel(c)) + '</span>' +
      '<span>' + esc(c.place || '地点待定') + '</span>' +
      '<span>' + esc(c.teacher || '教师待定') + '</span>' +
      '</div>';
    el.onclick = function () { showDetail(c); };
    return el;
  }

  /* "1-2节 08:00-09:40" */
  function sectionLabel(c) {
    var base = c.sections || '';
    return c.time_text ? base + ' ' + c.time_text : base;
  }

  // ---------------- 详情弹层 ----------------
  function showDetail(c) {
    var card = $('detail-card');
    var badge = c.is_elective ? '<span class="tag">选修课</span>' : '';
    var rows = '';
    if (c.is_elective) {
      rows =
        row('🕐', (c.weeks_raw || '见教务系统') + badge) +
        row('📍', esc(c.place || '待定') + (c.campus ? ' · ' + esc(c.campus) : '')) +
        row('👤', esc(c.teacher || '待定')) +
        row('🎓', esc(String(c.credit || '-')) + ' 学分 · ' + esc(c.category || '通识选修课'));
    } else {
      rows =
        row('🕐', esc(sectionLabel(c)) + (c.weeks_raw ? '（' + esc(c.weeks_raw) + '）' : '')) +
        row('📍', esc(c.place || '待定') + (c.campus ? ' · ' + esc(c.campus) : '')) +
        row('👤', esc(c.teacher || '待定')) +
        row('🎓', esc(String(c.credit || '-')) + ' 学分' +
            (c.evaluation_mode ? ' · ' + esc(c.evaluation_mode) : '')) +
        row('📖', esc(String(c.weekly_hours || '-')) + ' 学时/周');
    }
    card.innerHTML =
      '<div class="detail-head">' +
      '<h2>' + esc(c.title) + '</h2>' +
      '<div class="d-teacher">' + esc(c.teacher || '教师待定') +
      (c.class_name ? ' · ' + esc(c.class_name) : '') + '</div>' +
      '</div>' + rows +
      '<button class="detail-close" id="detail-close-btn">关闭</button>';
    openModal($('detail-mask'));
  }

  function row(k, v) {
    return '<div class="detail-row"><span class="k">' + k + '</span><span class="v">' + v + '</span></div>';
  }

  function openModal(mask) {
    mask.classList.remove('hidden', 'closing');
    // 锁住底层页面滚动：弹层打开时滑动只作用于弹层内部
    document.body.style.overflow = 'hidden';
  }

  function closeModal(mask) {
    mask.classList.add('closing');
    setTimeout(function () {
      mask.classList.add('hidden');
      mask.classList.remove('closing');
    }, 300);
    // 还有一个弹层开着就不解锁
    var masks = document.querySelectorAll('.detail-mask');
    var stillOpen = false;
    for (var i = 0; i < masks.length; i++) {
      if (masks[i] !== mask && !masks[i].classList.contains('hidden')) stillOpen = true;
    }
    if (!stillOpen) document.body.style.overflow = '';
  }

  // ---------------- 删除课表 ----------------
  function askDelete() {
    if (!data) return;
    $('confirm-text').textContent =
      '将删除本地保存的 ' + data.year + ' 学年 第 ' + data.term +
      ' 学期课表（' + data.count + ' 门）。删除后需重新登录才能再次查看。';
    openModal($('confirm-mask'));
  }

  function doDelete() {
    closeModal($('confirm-mask'));
    if (window.AndroidSchedule && window.AndroidSchedule.deleteSchedule) {
      if (window.AndroidSchedule.deleteSchedule()) {
        data = null;
        showEmpty();
      } else {
        alert('删除失败，请重试');
      }
      return;
    }
    if (window.DELETE_HANDLER) { window.DELETE_HANDLER(); return; }
    var msg = '删除课表请在电脑上运行：\n' +
      'python main.py --delete --year ' + data.year + ' --term ' + data.term;
    if (window.AndroidSchedule) {
      msg = '已退出删除确认。' + msg;
    }
    alert(msg);
  }

  function bindUI() {
    // 事件委托：innerHTML 重写后依然有效（detail-close-btn / day-back 等）
    document.addEventListener('click', function (e) {
      var t = e.target;
      if (t.id === 'detail-close-btn' || t.id === 'detail-cancel-btn') {
        closeModal($('detail-mask'));
      } else if (t.id === 'day-back') {
        closeDayView();
      } else if (t.id === 'confirm-ok') {
        doDelete();
      } else if (t.id === 'confirm-cancel') {
        closeModal($('confirm-mask'));
      } else if (t.id === 'log-close-btn') {
        closeModal($('log-mask'));
      } else if (t.id === 'notif-close-btn') {
        closeModal($('notif-mask'));
      } else if (t.id === 'notif-detail-close') {
        closeModal($('notif-detail-mask'));
      }
    });
    $('detail-mask').onclick = function (e) { if (e.target === this) closeModal(this); };
    $('notif-mask').onclick = function (e) { if (e.target === this) closeModal(this); };
    $('notif-detail-mask').onclick = function (e) { if (e.target === this) closeModal(this); };
    $('btn-delete').onclick = askDelete;
    $('confirm-mask').onclick = function (e) {
      if (e.target === this) closeModal(this);
    };
    $('btn-menu').onclick = openDrawer;
    $('sidebar-mask').onclick = closeDrawer;
    // 日志按钮入口已隐藏（功能保留）：$('btn-log').onclick = showLog;
    $('btn-bell').onclick = showNotifList;
    $('notif-clear-read').onclick = clearReadNotifications;
    $('fab-today').onclick = goThisWeek;
    updateBellDot();
    bindSwipeGestures();
    $('btn-refresh').onclick = function () {
      // 原生：重开 WebView 进教务首页（会话活着静默拉课表，过期重新登录）
      if (window.AndroidSchedule && window.AndroidSchedule.refreshSchedule) {
        window.AndroidSchedule.refreshSchedule();
        return;
      }
      if (window.REFRESH_HANDLER) { window.REFRESH_HANDLER(); return; }
      alert('更新课表请在电脑上运行：\n' +
        'python main.py --year ' + (data ? data.year : 2026) +
        ' --term ' + (data ? data.term : 1) + ' --update\n然后用新数据重新打包。');
    };
  }

  /* 日志弹层：把原生侧记录的操作日志显示出来（便于无 USB 线时排查）
   * 功能保留，入口已隐藏（铃铛占位）——需要时取消 index.html 里 btn-log 的注释 */
  function showLog() {
    var text = '(暂无日志)';
    if (window.AndroidSchedule && window.AndroidSchedule.readLog) {
      var raw = window.AndroidSchedule.readLog();
      if (raw) text = raw;
    }
    $('log-text').value = text;
    openModal($('log-mask'));
  }

  // ---------------- 通知中心（节假日/换课提醒） ----------------

  function notifApi() {
    return (window.AndroidSchedule && window.AndroidSchedule.getNotifications)
      ? window.AndroidSchedule : null;
  }

  /* 铃铛红点：有未读才显示。启动/操作后调用刷新 */
  function updateBellDot() {
    var bell = $('btn-bell');
    if (!bell) return;
    var api = notifApi();
    if (!api) { bell.classList.remove('has-dot'); return; }
    var list = [];
    try { list = JSON.parse(api.getNotifications() || '[]'); } catch (e) {}
    var unread = 0;
    list.forEach(function (n) { if (!n.read) unread++; });
    bell.classList.toggle('has-dot', unread > 0);
  }

  function fmtNotifTime(s) {
    // "2026-10-01 09:05" → "10-01 09:05"（今年省年份；跨年保留）
    return String(s || '').replace(/^\d{4}-/, '');
  }

  /* 通知面板：卡片列表（未读加粗+左侧蓝条，新的在上） */
  function showNotifList() {
    var api = notifApi();
    var box = $('notif-list');
    if (!api) {
      box.innerHTML = '<div class="notif-empty">暂无通知</div>';
    } else {
      var list = [];
      try { list = JSON.parse(api.getNotifications() || '[]'); } catch (e) {}
      if (!list.length) {
        box.innerHTML = '<div class="notif-empty">暂无通知</div>';
      } else {
        box.innerHTML = '';
        list.forEach(function (n) {
          var card = document.createElement('div');
          card.className = 'notif-item' + (n.read ? '' : ' unread');
          card.__notifId = n.id;
          card.innerHTML =
            '<div class="n-title">' + esc(n.title) +
              (n.read ? '' : '<span class="n-dot"></span>') + '</div>' +
            '<div class="n-date">' + esc(fmtNotifTime(n.date)) + '</div>';
          card.onclick = function () { showNotifDetail(n); };
          box.appendChild(card);
        });
      }
    }
    // 没有已读项时"清除已读"置灰
    updateClearReadBtn();
    openModal($('notif-mask'));
  }

  function updateClearReadBtn() {
    var btn = $('notif-clear-read');
    if (!btn) return;
    var api = notifApi();
    var hasRead = false;
    if (api) {
      try {
        JSON.parse(api.getNotifications() || '[]').forEach(function (n) {
          if (n.read) hasRead = true;
        });
      } catch (e) {}
    }
    btn.disabled = !hasRead;
  }

  /* 通知详情：点开即转已读、红点消失 */
  function showNotifDetail(n) {
    var api = notifApi();
    if (api && api.markNotificationRead && !n.read) {
      api.markNotificationRead(n.id);
      n.read = true;
      updateBellDot();
      // 列表里同步转已读样式
      var items = document.querySelectorAll('#notif-list .notif-item');
      for (var i = 0; i < items.length; i++) {
        if (items[i].__notifId === n.id) {
          items[i].classList.remove('unread');
          var dot = items[i].querySelector('.n-dot');
          if (dot) dot.remove();
        }
      }
      updateClearReadBtn();
    }
    $('notif-detail-title').textContent = n.title || '';
    $('notif-detail-date').textContent = '时间：' + fmtNotifTime(n.date);
    $('notif-detail-body').textContent = n.content || '';
    openModal($('notif-detail-mask'));
  }

  /* 清除已读：只能删已读的（原生侧也强制） */
  function clearReadNotifications() {
    var api = notifApi();
    if (!api || !api.deleteReadNotifications) return;
    api.deleteReadNotifications();
    showNotifList();   // 重新拉列表刷新
    updateBellDot();
  }

  // ---------------- 回到本周悬浮按钮 ----------------

  /* 浏览的周 != 本周时显示；本周/无数据时隐藏 */
  function updateFabToday() {
    var fab = $('fab-today');
    if (!fab) return;
    var today = data ? (data.today || {}) : {};
    var isThisWeek = data && today.in_term && today.today_week === currentWeek;
    var show = !!data && today.in_term && !isThisWeek;
    if (show) {
      fab.classList.remove('hidden');
      // 强制 reflow 后再加 show 类，保证过渡动画触发
      void fab.offsetWidth;
      fab.classList.add('show');
    } else {
      fab.classList.remove('show');
      // 等淡出动画结束再 display:none
      setTimeout(function () {
        if (!fab.classList.contains('show')) fab.classList.add('hidden');
      }, 300);
    }
  }

  function goThisWeek() {
    if (!data || !data.today || !data.today.in_term) return;
    if (currentWeek === data.today.today_week) return;
    // 与手势同款方向缓动，之后 FAB 淡出
    switchWeek(data.today.today_week > currentWeek ? 'next' : 'prev',
      data.today.today_week);
  }

  // ---------------- 左右滑切周（主界面手势） ----------------

  function bindSwipeGestures() {
    var startX = 0, startY = 0, tracking = false;

    document.addEventListener('touchstart', function (e) {
      if (e.touches.length !== 1) { tracking = false; return; }
      // 弹层打开（body 已锁滚）或当日详情页打开时不响应，
      // 只在课表主界面生效
      if (document.body.style.overflow === 'hidden') { tracking = false; return; }
      if (!$('day-view').classList.contains('hidden')) {
        tracking = false; return;
      }
      // 落在今日胶囊上不跟踪：胶囊自己横向滚动，
      // 在它上面左右滑是滚胶囊，不是切周
      var t0 = e.target;
      if (t0 && t0.closest && t0.closest('.today-strip')) {
        tracking = false;
        return;
      }
      tracking = true;
      startX = e.touches[0].clientX;
      startY = e.touches[0].clientY;
    }, { passive: true });

    document.addEventListener('touchend', function (e) {
      if (!tracking || !data) { tracking = false; return; }
      tracking = false;
      var t = e.changedTouches[0];
      var dx = t.clientX - startX;
      var dy = t.clientY - startY;
      // 水平位移够大、且明显是横向意图（避免误触竖直滚动）；
      // 纵向抖动过大也放弃（判定为滚动）
      if (Math.abs(dx) < 60 || Math.abs(dx) < Math.abs(dy) * 1.5) return;
      if (Math.abs(dy) > 40) return;
      if (dx < 0) {
        nextWeek();   // 左滑 → 下一周
      } else {
        prevWeek();   // 右滑 → 上一周
      }
    }, { passive: true });
  }

  /**
   * 带方向缓动的切周：翻页方向与内容滑动方向一致。
   * dir = 'next'（下一周）：旧内容往左移出，新内容从右侧滑入
   * dir = 'prev'（上一周）：旧内容往右移出，新内容从左侧滑入
   * 沿用全局 --ease/--dur（.3s）。
   */
  function switchWeek(dir, week) {
    if (!data) return;
    if (week < 1 || week > data.total_weeks) return;
    var box = $('schedule');
    // 动画进行中忽略重复触发
    if (box.dataset.switching === '1') return;
    box.dataset.switching = '1';

    // next：旧内容左移（-48）；prev：旧内容右移（+48）
    var outX = dir === 'next' ? -48 : 48;
    var inX = dir === 'next' ? 48 : -48;
    box.style.transition = 'opacity .18s var(--ease), transform .18s var(--ease)';
    box.style.opacity = '0';
    box.style.transform = 'translateX(' + outX + 'px)';

    setTimeout(function () {
      currentWeek = week;
      render();
      window.scrollTo({ top: 0 });
      // 新内容从旧内容移出的反方向滑入
      box.style.transition = 'none';
      box.style.transform = 'translateX(' + inX + 'px)';
      box.style.opacity = '0';
      void box.offsetWidth;   // 强制 reflow 保证过渡触发
      box.style.transition = 'opacity .18s var(--ease), transform .18s var(--ease)';
      box.style.opacity = '1';
      box.style.transform = 'translateX(0)';
      setTimeout(function () {
        box.dataset.switching = '0';
      }, 200);
    }, 180);
  }

  function nextWeek() {
    if (!data) return;
    if (currentWeek >= data.total_weeks) return;
    switchWeek('next', currentWeek + 1);
  }

  function prevWeek() {
    if (!data) return;
    if (currentWeek <= 1) return;
    switchWeek('prev', currentWeek - 1);
  }

  // ---------------- 侧边栏抽屉（手机） ----------------
  function openDrawer() {
    $('sidebar').classList.add('open');
    $('sidebar-mask').classList.remove('hidden');
  }
  function closeDrawer() {
    $('sidebar').classList.remove('open');
    $('sidebar-mask').classList.add('hidden');
  }

  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  // ---------------- 原生返回键 ----------------
  window.__onNativeBack = function () {
    if (!$('notif-detail-mask').classList.contains('hidden')) {
      closeModal($('notif-detail-mask'));
      return true;
    }
    if (!$('notif-mask').classList.contains('hidden')) {
      closeModal($('notif-mask'));
      return true;
    }
    if (!$('detail-mask').classList.contains('hidden')) {
      closeModal($('detail-mask'));
      return true;
    }
    if (!$('confirm-mask').classList.contains('hidden')) {
      closeModal($('confirm-mask'));
      return true;
    }
    if (!$('day-view').classList.contains('hidden')) {
      closeDayView();
      return true;
    }
    if (!$('log-mask').classList.contains('hidden')) {
      closeModal($('log-mask'));
      return true;
    }
    return false;
  };

  // ---------------- 启动 ----------------
  bindUI();
  loadData(function (d) {
    data = d;
    currentWeek = startWeek();
    render();
  });
})();
