<script setup lang="ts">
import { onMounted, ref } from 'vue'
import type { HealthResponse, Item, ItemCreate, ItemUpdate } from '@miniapp/api-contract'
import { request } from '@/utils/request'

const apiStatus = ref('检查中...')
const items = ref<Item[]>([])
const newTitle = ref('')
const loading = ref(false)

async function checkHealth() {
  try {
    const data = await request<HealthResponse>({ url: '/health' })
    apiStatus.value = `${data.service} · ${data.status}`
  } catch {
    apiStatus.value = 'API 暂不可用'
  }
}

async function loadItems() {
  try {
    items.value = await request<Item[]>({ url: '/items' })
  } catch {
    uni.showToast({ title: '读取数据失败', icon: 'none' })
  }
}

async function addItem() {
  const title = newTitle.value.trim()
  if (!title || loading.value) return

  loading.value = true
  try {
    const payload: ItemCreate = { title }
    const item = await request<Item>({
      url: '/items',
      method: 'POST',
      data: payload,
    })
    items.value.unshift(item)
    newTitle.value = ''
  } catch {
    uni.showToast({ title: '新增失败', icon: 'none' })
  } finally {
    loading.value = false
  }
}

async function toggleItem(item: Item) {
  try {
    const payload: ItemUpdate = { completed: !item.completed }
    const updated = await request<Item>({
      url: `/items/${item.id}`,
      method: 'PUT',
      data: payload,
    })
    Object.assign(item, updated)
  } catch {
    uni.showToast({ title: '更新失败', icon: 'none' })
  }
}

async function removeItem(item: Item) {
  try {
    await request<void>({ url: `/items/${item.id}`, method: 'DELETE' })
    items.value = items.value.filter((entry) => entry.id !== item.id)
  } catch {
    uni.showToast({ title: '删除失败', icon: 'none' })
  }
}

onMounted(async () => {
  await Promise.all([checkHealth(), loadItems()])
})
</script>

<template>
  <view class="page-shell">
    <view class="hero">
      <text class="eyebrow">UNIAPP · FASTAPI · TRELLIS</text>
      <text class="title">全栈小程序起始框架</text>
      <text class="subtitle">一套 Vue 代码，可编译为微信小程序、H5、Android 和 iOS。</text>
      <view class="status-pill">
        <view class="status-dot" :class="{ online: apiStatus.includes('ok') }" />
        <text>{{ apiStatus }}</text>
      </view>
    </view>

    <view class="content-card">
      <view class="section-heading">
        <view>
          <text class="section-title">示例任务</text>
          <text class="section-caption">用于验证前后端接口已连通</text>
        </view>
        <button class="refresh-button" size="mini" @click="loadItems">刷新</button>
      </view>

      <view class="composer">
        <input
          v-model="newTitle"
          class="composer-input"
          maxlength="80"
          placeholder="输入一项要完成的事情"
          confirm-type="done"
          @confirm="addItem"
        />
        <button class="add-button" size="mini" :loading="loading" @click="addItem">添加</button>
      </view>

      <view v-if="items.length" class="item-list">
        <view v-for="item in items" :key="item.id" class="item-row">
          <view class="item-main" @click="toggleItem(item)">
            <view class="check-box" :class="{ checked: item.completed }">
              <text v-if="item.completed">✓</text>
            </view>
            <text class="item-title" :class="{ completed: item.completed }">{{ item.title }}</text>
          </view>
          <button class="delete-button" size="mini" @click="removeItem(item)">删除</button>
        </view>
      </view>
      <view v-else class="empty-state">
        <text>还没有任务，先添加一项吧。</text>
      </view>
    </view>

    <view class="footer-note">
      <text>API 文档：/docs · OpenAPI：/openapi.json</text>
    </view>
  </view>
</template>

<style scoped>
.page-shell {
  min-height: 100vh;
  padding: 48rpx 32rpx;
  box-sizing: border-box;
}

.hero {
  padding: 24rpx 8rpx 44rpx;
}

.eyebrow {
  display: block;
  color: #2563eb;
  font-size: 22rpx;
  font-weight: 700;
  letter-spacing: 2rpx;
}

.title {
  display: block;
  margin-top: 18rpx;
  color: #0f172a;
  font-size: 48rpx;
  font-weight: 800;
  line-height: 1.2;
}

.subtitle {
  display: block;
  margin-top: 18rpx;
  color: #64748b;
  font-size: 26rpx;
  line-height: 1.6;
}

.status-pill {
  display: inline-flex;
  align-items: center;
  gap: 12rpx;
  margin-top: 26rpx;
  padding: 12rpx 18rpx;
  border: 1px solid #dbeafe;
  border-radius: 999rpx;
  background: #eff6ff;
  color: #1d4ed8;
  font-size: 23rpx;
}

.status-dot {
  width: 14rpx;
  height: 14rpx;
  border-radius: 50%;
  background: #f59e0b;
}

.status-dot.online {
  background: #16a34a;
}

.content-card {
  padding: 30rpx;
  border: 1px solid #e2e8f0;
  border-radius: 18rpx;
  background: #ffffff;
  box-shadow: 0 16rpx 36rpx rgba(15, 23, 42, 0.06);
}

.section-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
}

.section-title,
.section-caption {
  display: block;
}

.section-title {
  color: #0f172a;
  font-size: 32rpx;
  font-weight: 700;
}

.section-caption {
  margin-top: 8rpx;
  color: #64748b;
  font-size: 23rpx;
}

.refresh-button,
.add-button,
.delete-button {
  border: 0;
  border-radius: 10rpx;
  font-size: 23rpx;
}

.refresh-button {
  color: #2563eb;
  background: #eff6ff;
}

.composer {
  display: flex;
  gap: 16rpx;
  margin-top: 28rpx;
}

.composer-input {
  flex: 1;
  height: 72rpx;
  padding: 0 20rpx;
  box-sizing: border-box;
  border: 1px solid #cbd5e1;
  border-radius: 10rpx;
  color: #0f172a;
  font-size: 26rpx;
}

.add-button {
  min-width: 100rpx;
  color: #ffffff;
  background: #2563eb;
}

.item-list {
  margin-top: 24rpx;
}

.item-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16rpx;
  min-height: 82rpx;
  border-bottom: 1px solid #f1f5f9;
}

.item-main {
  display: flex;
  align-items: center;
  flex: 1;
  gap: 16rpx;
  min-width: 0;
}

.check-box {
  display: flex;
  align-items: center;
  justify-content: center;
  flex: 0 0 auto;
  width: 34rpx;
  height: 34rpx;
  border: 2rpx solid #94a3b8;
  border-radius: 8rpx;
  color: #ffffff;
  font-size: 24rpx;
}

.check-box.checked {
  border-color: #16a34a;
  background: #16a34a;
}

.item-title {
  overflow: hidden;
  color: #334155;
  font-size: 26rpx;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.item-title.completed {
  color: #94a3b8;
  text-decoration: line-through;
}

.delete-button {
  color: #dc2626;
  background: #fef2f2;
}

.empty-state {
  padding: 52rpx 0 28rpx;
  color: #94a3b8;
  font-size: 25rpx;
  text-align: center;
}

.footer-note {
  padding: 28rpx 8rpx;
  color: #94a3b8;
  font-size: 22rpx;
  text-align: center;
}
</style>
