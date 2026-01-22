/**
 * Service Worker for L1 Advisory Layer
 * 
 * 功能：
 * 1. 实现浏览器级全局通知（即使页面关闭也能接收）
 * 2. 缓存静态资源
 * 3. 离线支持
 */

const CACHE_NAME = 'l1-advisory-v1';
const urlsToCache = [
    '/',
    '/static/css/style_l1.css',
    '/static/js/app_l1.js'
];

// 安装Service Worker
self.addEventListener('install', event => {
    console.log('[Service Worker] Installing...');
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then(cache => {
                console.log('[Service Worker] Caching app shell');
                return cache.addAll(urlsToCache);
            })
    );
});

// 激活Service Worker
self.addEventListener('activate', event => {
    console.log('[Service Worker] Activating...');
    event.waitUntil(
        caches.keys().then(cacheNames => {
            return Promise.all(
                cacheNames.map(cacheName => {
                    if (cacheName !== CACHE_NAME) {
                        console.log('[Service Worker] Deleting old cache:', cacheName);
                        return caches.delete(cacheName);
                    }
                })
            );
        })
    );
});

// 拦截请求
self.addEventListener('fetch', event => {
    event.respondWith(
        caches.match(event.request)
            .then(response => {
                // 缓存命中，返回缓存
                if (response) {
                    return response;
                }
                // 未命中，从网络获取
                return fetch(event.request);
            })
    );
});

// 接收消息（从主页面发送）
self.addEventListener('message', event => {
    console.log('[Service Worker] Received message:', event.data);
    
    if (event.data && event.data.type === 'SHOW_NOTIFICATION') {
        const { title, body, icon, tag, data } = event.data.notification;
        
        self.registration.showNotification(title, {
            body: body,
            icon: icon || '/static/favicon.ico',
            badge: '🔔',
            tag: tag,
            requireInteraction: false,
            data: data,
            actions: [
                {
                    action: 'view',
                    title: '查看详情'
                },
                {
                    action: 'close',
                    title: '关闭'
                }
            ]
        });
    }
});

// 通知点击事件
self.addEventListener('notificationclick', event => {
    console.log('[Service Worker] Notification clicked:', event.action);
    
    event.notification.close();
    
    if (event.action === 'view') {
        // 打开或聚焦应用页面
        event.waitUntil(
            clients.matchAll({ type: 'window', includeUncontrolled: true })
                .then(clientList => {
                    // 如果已有打开的窗口，聚焦它
                    for (let client of clientList) {
                        if (client.url.includes(self.registration.scope) && 'focus' in client) {
                            return client.focus();
                        }
                    }
                    // 否则打开新窗口
                    if (clients.openWindow) {
                        return clients.openWindow('/');
                    }
                })
        );
    }
});

// 推送通知（如果需要服务器推送）
self.addEventListener('push', event => {
    console.log('[Service Worker] Push received');
    
    if (event.data) {
        const data = event.data.json();
        
        event.waitUntil(
            self.registration.showNotification(data.title, {
                body: data.body,
                icon: data.icon || '/static/favicon.ico',
                badge: '🔔',
                data: data.data
            })
        );
    }
});
