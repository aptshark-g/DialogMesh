# Gateway 页面 "保存即刷新" — 完整链路审计

## 点击保存 → 数据流

```
1. 用户点击 "保存"
2. handleSaveConfig(name) → configProvider(name, {api_key, base_url})
3. useV6Gateway.configProvider:
   a. setData({saveLoading: true})          → 触发渲染 (按钮变"保存中...")
   b. await configGatewayProvider(name, req) → PUT /v6/gateway/providers/{name}
   c. await fetchGatewayProviders()          → GET /v6/gateway/providers
      └─ fetchGatewayProviders 内部 setData({providersLoading: true}) → 又触发渲染
      └─ 成功后 setData({gatewayProviders: new, providersLoading: false})
   d. setData({saveLoading: false})
4. gatewayProviders 引用变化 → GatewayPage useEffect 触发
5. useEffect 遍历 new providers → 填充 configForms
```

## 切换到其他页再回来 → 数据丢失

```
1. 离开 GatewayPage → 组件卸载 → configForms={} 丢失
2. 回到 GatewayPage → 组件重新挂载 → configForms 初始化为 {}
3. useV6Gateway hook 可能已缓存数据 (useRef/useState in hook 不随组件卸载)
4. refreshAll() 立即执行 → 可能成功拿到数据
5. 但如果 API 慢/断 → fetchGatewayProviders catch → 保留 prev.gatewayProviders
6. prev.gatewayProviders 可能是 null (首次挂载)
7. useEffect 中 list.length===0 → 不填充 configForms → 表单全空
```

## 根因

| 问题 | 位置 | 修复 |
|------|------|------|
| configForms 是页面局部状态 | GatewayPage.tsx:85 | 路由切换丢失 |
| 首次挂载 gatewayProviders 可能为 null | useV6Gateway.ts:148 | 删除 DEFAULT_PROVIDERS(已做) |
| useEffect 只在 providers.length>0 时填充 | GatewayPage.tsx:140 | 缺少初始化逻辑 |
| 保存后 fetchGatewayProviders 触发 loading 闪烁 | useV6Gateway.ts:160 | 保存成功后不应 reload full list |

## 修复方案

1. configForms → localStorage 持久化 (简单有效)
2. 首次挂载时立即从 localStorage 恢复
3. 保存成功后直接更新 configForms，不等 reload
