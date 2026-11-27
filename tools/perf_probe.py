#!/usr/bin/env python3
"""tools/perf_probe.py — deck 加载性能探针（FCP / LCP / DCL / 长任务 / 传输字节）

用法：
    python3 tools/perf_probe.py <url>                       # 本地 wifi、不降速
    python3 tools/perf_probe.py <url> --cpu 4 --net slow4g  # 4× CPU + 1.6 Mbps / 150 ms RTT
    python3 tools/perf_probe.py <url> --block-images        # 只看 HTML + JS 的成本
    python3 tools/perf_probe.py <url> --label 改前           # 结果里带标签，方便对比

输出一行 JSON（导航时序、paint、LCP、长任务、每个资源的字节与耗时）。
方法说明见 docs/PERFORMANCE.md。
"""
import argparse
import json
import sys

from playwright.sync_api import sync_playwright

# 在页面里挂 PerformanceObserver：LCP 与 longtask 都要在导航前注入才收得到
INIT_JS = """
window.__perf = { lcp: 0, longtasks: [], longtaskTotal: 0 };
try {
  new PerformanceObserver(list => {
    for (const e of list.getEntries()) { window.__perf.lcp = e.startTime; }
  }).observe({ type: 'largest-contentful-paint', buffered: true });
} catch (e) {}
try {
  new PerformanceObserver(list => {
    for (const e of list.getEntries()) {
      window.__perf.longtasks.push(Math.round(e.startTime + e.duration));
      window.__perf.longtaskTotal += e.duration;
    }
  }).observe({ type: 'longtask', buffered: true });
} catch (e) {}
"""

COLLECT_JS = """
() => {
  const nav = performance.getEntriesByType('navigation')[0] || {};
  const res = performance.getEntriesByType('resource').map(r => ({
    name: r.name.split('/').slice(-1)[0],
    initiator: r.initiatorType,
    bytes: r.transferSize || r.encodedBodySize || 0,
    ms: Math.round(r.duration),
    start: Math.round(r.startTime),
  }));
  return {
    navigation: {
      responseEnd: Math.round(nav.responseEnd || 0),
      domInteractive: Math.round(nav.domInteractive || 0),
      domContentLoaded: Math.round(nav.domContentLoadedEventEnd || 0),
      loadEvent: Math.round(nav.loadEventEnd || 0),
      domNodes: nav.domComplete || 0,
    },
    paint: performance.getEntriesByType('paint').map(p => [p.name, Math.round(p.startTime)]),
    lcp: Math.round(window.__perf ? window.__perf.lcp : 0),
    longtasks: window.__perf ? window.__perf.longtasks : [],
    longtaskTotal: window.__perf ? Math.round(window.__perf.longtaskTotal) : 0,
    resources: res,
  };
}
"""

# 网络档位：latency 毫秒；down/up 字节每秒（Chrome DevTools 同款口径）
NETS = {
    'wifi': dict(latency=30, down=30 * 1024 * 1024 / 8, up=10 * 1024 * 1024 / 8),
    'slow4g': dict(latency=150, down=1.6 * 1024 * 1024 / 8, up=750 * 1024 / 8),
    'fast3g': dict(latency=300, down=1.6 * 1024 * 1024 / 8, up=750 * 1024 / 8),
}


def main():
    ap = argparse.ArgumentParser(description='deck 加载性能探针')
    ap.add_argument('url')
    ap.add_argument('--cpu', type=int, default=1, help='CPU 降速倍数，如 4')
    ap.add_argument('--net', default='wifi', choices=sorted(NETS), help='网络档位')
    ap.add_argument('--block-images', action='store_true', help='屏蔽 jpg/png/webp，只看 HTML+JS')
    ap.add_argument('--label', default='run', help='结果里的标签')
    ap.add_argument('--settle', type=int, default=1200, help='load 后再等多少毫秒收 LCP/长任务')
    a = ap.parse_args()

    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=['--disable-dev-shm-usage'])
        ctx = browser.new_context(viewport={'width': 1600, 'height': 900})
        ctx.add_init_script(INIT_JS)
        page = ctx.new_page()
        cdp = ctx.new_cdp_session(page)
        cdp.send('Network.enable')
        cdp.send('Network.setCacheDisabled', {'cacheDisabled': True})   # 冷缓存
        net = NETS[a.net]
        cdp.send('Network.emulateNetworkConditions', {
            'offline': False, 'latency': net['latency'],
            'downloadThroughput': net['down'], 'uploadThroughput': net['up'],
        })
        if a.cpu > 1:
            cdp.send('Emulation.setCPUThrottlingRate', {'rate': a.cpu})
        if a.block_images:
            page.route('**/*.{jpg,jpeg,png,webp}', lambda route: route.abort())

        page.goto(a.url, wait_until='load', timeout=180000)
        page.wait_for_timeout(a.settle)
        data = page.evaluate(COLLECT_JS)
        browser.close()

    data.update(label=a.label, cpu=a.cpu, net=a.net, blockImages=a.block_images,
                resCount=len(data['resources']),
                resBytesKB=round(sum(r['bytes'] for r in data['resources']) / 1024))
    print(json.dumps(data, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
