# 多平台编译与发布

## 微信小程序

```bash
pnpm dev:weixin
pnpm build:weixin
```

将以下目录导入微信开发者工具：

```text
apps/miniapp/dist/build/mp-weixin
```

发布前检查：

1. `src/manifest.json` 填写正式 AppID。
2. 配置 request、upload、download 等合法域名。
3. 使用 HTTPS API。
4. 在真机上验证登录、支付、定位和文件上传。
5. 在微信公众平台提交审核。

## H5 网站

```bash
pnpm build:h5
```

静态文件通常在 `apps/miniapp/dist/build/h5`。Nginx 示例：

```nginx
server {
    listen 80;
    server_name example.com;
    root /srv/miniapp;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8000/api/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

若网站需要强 SEO（官网、内容站、公开电商首页），建议另建 Nuxt 站点；UniApp H5 更适合业务型 SPA。

## Android / iOS

```bash
pnpm build:app
```

该命令生成供 App 容器使用的 Web 资源，不会直接生成安装包。App 目标一般
还需要使用 HBuilderX 发行和云打包：

- Android：配置 applicationId、签名证书，发布 APK/AAB。
- iOS：配置 Apple Developer、Bundle ID、证书和 Provisioning Profile，生成 IPA 后提交 App Store Connect。

复杂蓝牙、NFC、后台任务、推送、音视频或系统级能力可能需要 UniApp 原生插件；平台差异代码用条件编译隔离。

## API 地址

开发时可通过 `VITE_API_BASE_URL` 覆盖默认地址：

```bash
VITE_API_BASE_URL=https://api.example.com/api/v1 pnpm build:h5
VITE_API_BASE_URL=https://api.example.com/api/v1 pnpm build:weixin
VITE_API_BASE_URL=https://api.example.com/api/v1 pnpm build:app
```

小程序和 App 的 API 域名必须使用公网可访问的 HTTPS 地址；不要把本机 `127.0.0.1` 带进生产包。
