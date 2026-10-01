/** 网站公共外壳
它负责：
- 顶部品牌名称。
- 全局搜索。
- 当前任务按钮。
- 系统消息按钮。
- 用户入口。
- 左侧八个一级菜单。
- 当前页面标题和说明。
- 当前日期时间。
- Mock 演示标记。
- 二级页签。
- 中间业务页面出口 <router-view />。
- 页面底部的业务能力入口。
- 页脚。
- 任务抽屉、通知抽屉和用户信息弹窗。
 */

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { navigation } from '../router/navigation'  /** 导入菜单配置 */
import AppIcon from '../components/AppIcon.vue'
import TaskTable from '../components/TaskTable.vue'
import CapabilityDock from '../components/CapabilityDock.vue'
import { usePlatformStore } from '../stores/platform'
import { isMock } from '../api/request'  /** 判断是否是 Mock模式 */
const route = useRoute()
const router = useRouter()
const store = usePlatformStore()
/** 判断当前选中哪个菜单 */
const current = computed(
  () =>
    navigation.find((item) => route.path.startsWith(item.path + '/') || route.path === item.path) ||
    navigation[0]!,
)
const query = ref('')  /** 保存用户输入的搜索内容 */
const isTasksOpen = ref(false)
const isNoticeOpen = ref(false)
const isProfileOpen = ref(false)
const hasUnread = ref(true)
const now = ref(new Date()) 
const timer = setInterval(() => {
  now.value = new Date()
}, 1000)
onUnmounted(() => clearInterval(timer))  
onMounted(() => store.fetchTasks().catch(() => undefined))
/** 生成搜索结果：他会读取navigation.ts中的所有一级和二级页签，然后整理成可以搜索的数据 */
const matches = computed(() =>
  navigation
    .flatMap((item) => [
      { value: item.title, path: item.path },
      ...item.tabs.filter((tab) => item.path !== '/data-governance' || tab.path === 'process').map((tab) => ({
        value: `${item.title} / ${tab.title}`,
        path: `${item.path}/${tab.path}`,
      })),
    ])
    .filter((item) => item.value.includes(query.value)), /** 筛选出名称中包含搜索文字的菜单 */
)
/** 搜索页面 */
function searchPages(value: string, callback: (items: { value: string; path: string }[]) => void) {
  query.value = value
  callback(matches.value)
}
/** 跳转页面 */
function selectPage(item: Record<string, unknown>) {
  router.push(String(item.path))
  query.value = ''
}
function openUserManagement() {
  router.push('/system/users')
  isProfileOpen.value = false
}
</script>
<template>
  <div class="app-shell">
    <header class="topbar">
      <router-link to="/dashboard" class="brand"
        ><span class="brand-shield"><AppIcon name="Shield" /></span 
        ><strong>内容安全治理原型平台</strong></router-link
      ><span class="brand-tagline">AI赋能安全治理 · 构建清朗数字空间</span>
      <div class="top-actions">
        <el-autocomplete
          popper-class="global-search-dropdown"
          v-model="query"   
          :fetch-suggestions="searchPages"
          placeholder="搜索功能、数据、任务等…"
          aria-label="全局搜索"
          @select="selectPage"
          ><template #prefix><AppIcon name="Search" /></template></el-autocomplete
        >
        <button class="top-button" @click="isTasksOpen = true">
          <AppIcon name="Tickets" />当前任务
          <b>{{ store.tasks.filter((task) => task.status === 'running').length }}</b></button
        >
        <button
          class="top-button notice-button"
          aria-label="系统消息"
          @click="isNoticeOpen = true"
        >
          <AppIcon name="BellFilled" /><i v-if="hasUnread"></i></button
        >
        <button class="top-button user-button" @click="isProfileOpen = true">
          <span class="avatar">张</span>张三<AppIcon name="ArrowDown" />
        </button>
      </div>
    </header>

    <!-- 左侧菜单显示代码 -->
    <aside class="sidebar">
      <nav aria-label="主导航">
        <router-link
          v-for="item in navigation"
          :key="item.path"
          :to="item.path"
          :class="{ active: current.path === item.path }"
          ><AppIcon :name="item.icon" /><span>{{ item.title }}</span
          ><AppIcon v-if="item.tabs.length" class="nav-arrow" name="ArrowDown"
        /></router-link>
      </nav>
      <div class="sidebar-bottom">
        <div class="cityscape"></div>
        <p>安全的内容<br />更美好的数字社会</p>
      </div>
    </aside>
    <main class="main-content">
      <div class="page-title">
        <div>
          <!-- 页面标题和描述 -->
          <h1>{{ current.title }}</h1>
          <span>{{ current.description }}</span>
        </div>
        <div class="page-meta">
          <div v-if="isMock" class="demo-label"><span></span>原型演示 · 示例数据</div>
          <!-- 时间 -->
          <time>
            {{ now.toLocaleDateString('zh-CN') }}
            {{ now.toLocaleDateString('zh-CN', { weekday: 'long' }) }}
            {{ now.toLocaleTimeString('zh-CN', { hour12: false }) }}</time
          ><span class="motto">让内容更安全 · 让社会更美好</span>
        </div>
      </div>
      <!-- 数据资源在父页面中维护自己的总览与子页面导航。 -->
      <nav v-if="current.tabs.length && !['/data-resource', '/data-governance', '/model-train', '/compliance', '/evaluation'].includes(current.path)" class="page-tabs" aria-label="页面子导航">
        <!-- 遍历当前模块配置的所有二级页签 -->
        <router-link
          v-for="(tab, index) in current.tabs"
          :key="tab.path"
          :to="`${current.path}/${tab.path}`"
          :class="{ selected: route.params.tab === tab.path || (!route.params.tab && index === 0) }"
          >
          <!-- 显示页签名称 -->
          {{ tab.title }}
        </router-link>
      </nav>
      <router-view v-slot="{ Component }">
        <Transition name="page-fade">
          <component :is="Component" />
        </Transition>
      </router-view>
      <CapabilityDock v-if="!['/data-resource', '/data-governance', '/model-train', '/compliance', '/evaluation'].includes(current.path)" />
      <footer class="page-footer">
        内容安全治理原型平台 <span>统一数据 · 智能治理 · 全程可溯</span>
      </footer>
    </main>
    <el-drawer v-model="isTasksOpen" title="当前任务" size="720px" class="current-tasks-drawer"><TaskTable /></el-drawer
    >
    <el-drawer v-model="isNoticeOpen" title="系统消息" size="400px" class="notice-drawer"
      ><el-button link type="primary" @click="hasUnread = false">全部标记已读</el-button>
      <div class="notification">
        <b>平台初始化完成</b>
        <p>八个业务模块已就绪，可通过左侧导航访问。</p>
        <small>系统通知 · {{ hasUnread ? '未读' : '已读' }}</small>
      </div>
      <div class="notification">
        <b>前端原型演示</b>
        <p>当前展示示例数据，业务能力等待后端接入。</p>
      </div></el-drawer
    >
    <el-dialog v-model="isProfileOpen" title="个人信息" width="420px" class="profile-dialog"
      ><el-descriptions :column="1" border
        ><el-descriptions-item label="用户">张三</el-descriptions-item
        ><el-descriptions-item label="角色">平台管理员（演示）</el-descriptions-item
        ><el-descriptions-item label="工作空间"
          >内容安全治理中心</el-descriptions-item
        ></el-descriptions
      ><template #footer
        ><el-button type="primary" @click="openUserManagement" class="profile-dialog">用户管理</el-button></template
      ></el-dialog
    >
  </div>
</template>
