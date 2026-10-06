<template>
  <!-- 未登录时展示内嵌登录页：管理后台唯一入口为 /chatbotadmin，登录态由本组件自管 -->
  <div v-if="!authed" class="admin-login-page">
    <div class="login-card">
      <div class="brand">
        <img :src="brandIcon" class="brand-img" alt="Confide" />
        <span class="brand-text">{{ t('管理后台', 'Admin Panel') }}</span>
      </div>
      <p class="subtitle">{{ t('管理员专用登录入口（账号密码由服务端 .env 配置）', 'Admin-only login. Credentials come from the server .env') }}</p>

      <el-form @submit.prevent="doLogin" class="login-form">
        <el-form-item>
          <el-input
            v-model="loginUsername"
            :placeholder="t('管理员账号', 'Admin username')"
            size="large"
            autocomplete="username"
            :prefix-icon="User"
          />
        </el-form-item>
        <el-form-item>
          <el-input
            v-model="loginPassword"
            type="password"
            :placeholder="t('管理员密码', 'Admin password')"
            size="large"
            show-password
            autocomplete="current-password"
            :prefix-icon="Lock"
            @keyup.enter="doLogin"
          />
        </el-form-item>
        <el-button
          type="primary"
          class="login-btn"
          size="large"
          :loading="loginLoading"
          @click="doLogin"
        >
          {{ t('登 录', 'Login') }}
        </el-button>
      </el-form>

      <div class="back-link">
        <el-button link type="primary" @click="router.push('/')">
          {{ t('返回 Confide 主界面', 'Back to Confide') }}
        </el-button>
      </div>
    </div>
  </div>

  <div v-else class="admin-page">
    <!-- 顶部导航 -->
    <header class="admin-header">
      <div class="header-brand">
        <img :src="brandIcon" class="brand-img" alt="Confide" />
        <span class="brand-text">{{ t('Confide 管理后台', 'Confide Admin') }}</span>
      </div>
      <div class="header-right">
        <span v-if="adminName" class="admin-name">
          <el-icon><Monitor /></el-icon> {{ t('管理员', 'Admin') }}：{{ adminName }}
        </span>
        <el-button size="small" :icon="Back" @click="$router.push('/')">
          {{ t('返回主界面', 'Back to app') }}
        </el-button>
        <el-button size="small" type="danger" plain :icon="SwitchButton" @click="doLogout">
          {{ t('退出', 'Log out') }}
        </el-button>
      </div>
    </header>

    <main class="admin-main">
      <!-- 平台统计 -->
      <div class="admin-stats" v-loading="statsLoading">
        <div class="stat-card"><div class="stat-num">{{ stats.user_count ?? '-' }}</div><div class="stat-label">{{ t('用户', 'Users') }}</div></div>
        <div class="stat-card"><div class="stat-num">{{ stats.conversation_count ?? '-' }}</div><div class="stat-label">{{ t('对话', 'Conversations') }}</div></div>
        <div class="stat-card"><div class="stat-num">{{ stats.message_count ?? '-' }}</div><div class="stat-label">{{ t('消息', 'Messages') }}</div></div>
        <div class="stat-card"><div class="stat-num">{{ stats.provider_count ?? '-' }}</div><div class="stat-label">{{ t('模型配置', 'Providers') }}</div></div>
        <div class="stat-card"><div class="stat-num">{{ stats.persona_count ?? '-' }}</div><div class="stat-label">{{ t('角色', 'Personas') }}</div></div>
        <div class="stat-card stat-today">
          <div class="stat-num">{{ (stats.today?.users ?? 0) }}<span class="sub">/{{ stats.today?.messages ?? 0 }}</span></div>
          <div class="stat-label">{{ t('今日新增用户/消息', 'New today') }}</div>
        </div>
      </div>

      <el-tabs v-model="activeTab" class="admin-tabs" @tab-change="onTabChange">
        <!-- 用户数据 Tab -->
        <el-tab-pane :label="t('用户数据', 'User Data')" name="users">
          <div class="admin-toolbar">
            <span class="admin-title">{{ t('用户数据', 'User Data') }}</span>
            <div class="toolbar-actions">
              <el-button size="small" :icon="Refresh" @click="loadAll">{{ t('刷新', 'Refresh') }}</el-button>
            </div>
          </div>

          <!-- 混合筛选：可只选一个条件，也可叠加多个条件 -->
          <div class="filter-panel">
            <el-input
              v-model="filters.keyword"
              :placeholder="t('用户名 / 邮箱关键词', 'Keyword: username or email')"
              size="small"
              clearable
              class="filter-input"
              @input="applyFilters"
            />
            <el-select
              v-model="filters.genders"
              multiple
              collapse-tags
              collapse-tags-tooltip
              :placeholder="t('性别', 'Gender')"
              size="small"
              class="filter-select"
              @change="applyFilters"
            >
              <el-option label="男" value="男" />
              <el-option label="女" value="女" />
              <el-option label="神秘" value="神秘" />
            </el-select>
            <el-select
              v-model="filters.statuses"
              multiple
              collapse-tags
              collapse-tags-tooltip
              :placeholder="t('账号状态', 'Status')"
              size="small"
              class="filter-select"
              @change="applyFilters"
            >
              <el-option :label="t('正常', 'Active')" value="active" />
              <el-option :label="t('停用', 'Disabled')" value="disabled" />
              <el-option :label="t('已注销', 'Deleted')" value="deleted" />
            </el-select>
            <el-select
              v-model="filters.activity"
              :placeholder="t('活跃度', 'Activity')"
              size="small"
              class="filter-select"
              clearable
              @change="applyFilters"
            >
              <el-option :label="t('有对话', 'Has chats')" value="has_conversation" />
              <el-option :label="t('有消息', 'Has messages')" value="has_message" />
              <el-option :label="t('从未对话', 'No chats')" value="no_conversation" />
              <el-option :label="t('今日活跃', 'Active today')" value="today" />
              <el-option :label="t('7 天内活跃', 'Active in 7d')" value="week" />
            </el-select>
            <el-select
              v-model="filters.hasConfig"
              multiple
              collapse-tags
              collapse-tags-tooltip
              :placeholder="t('配置情况', 'Config')"
              size="small"
              class="filter-select"
              @change="applyFilters"
            >
              <el-option :label="t('已配模型', 'Has provider')" value="provider" />
              <el-option :label="t('有人物卡', 'Has persona')" value="persona" />
              <el-option :label="t('有头像', 'Has avatar')" value="avatar" />
            </el-select>
            <el-button size="small" plain @click="resetFilters">{{ t('重置', 'Reset') }}</el-button>
            <el-select
              v-model="userSort"
              size="small"
              class="filter-select"
              @change="onUserSortChange"
            >
              <el-option :label="t('按注册时间', 'Registered')" value="created_at" />
              <el-option :label="t('按最近活跃', 'Last active')" value="last_active" />
              <el-option :label="t('按消息数', 'Messages')" value="message_count" />
              <el-option :label="t('按 Token', 'Tokens')" value="total_tokens" />
            </el-select>
            <span class="filter-count">{{ t('命中', 'Matched') }} {{ userTotal }}</span>
          </div>

          <el-table
            ref="userTableRef"
            :data="users"
            v-loading="usersLoading"
            class="admin-table"
            :default-expand-all="false"
            row-key="id"
            @expand-change="onUserExpand"
          >
            <el-table-column type="expand">
              <template #default="{ row }">
                <div class="inner-table-scroll">
                  <el-table
                    ref="convTableRef"
                    :data="row._conversations || []"
                    class="inner-table"
                    row-key="id"
                    :max-height="460"
                    scrollbar-always-on
                    v-loading="row._loading"
                    @selection-change="(sel) => onConvSelectChange(row, sel)"
                  >
                  <el-table-column type="selection" width="42" :selectable="(conv) => canSelectConv(conv)" />
                  <el-table-column prop="title" :label="t('对话标题', 'Conversation')" min-width="150" show-overflow-tooltip />
                  <el-table-column prop="message_count" :label="t('消息数', 'Msgs')" width="80" align="center">
                    <template #default="{ row: conv }">
                      <span class="msg-count-link" @click.stop="viewConversation(conv)">{{ conv.message_count }}</span>
                    </template>
                  </el-table-column>
                  <el-table-column :label="t('是否存在', 'Exists')" width="90" align="center">
                    <template #default="{ row: conv }">
                      <el-tag :type="conv.exists ? 'success' : 'info'" size="small" effect="plain">
                        {{ conv.exists ? t('存在', 'Yes') : t('已移除', 'Removed') }}
                      </el-tag>
                    </template>
                  </el-table-column>
                  <el-table-column :label="t('AI人设', 'AI Persona')" width="130" show-overflow-tooltip>
                    <template #default="{ row: conv }">
                      <span v-if="conv.persona_name" class="persona-link" @click.stop="showPersonaDetail(conv, 'ai')">{{ conv.persona_name }}</span>
                      <span v-else>-</span>
                    </template>
                  </el-table-column>
                  <el-table-column :label="t('背景图', 'Background')" width="90" align="center">
                    <template #default="{ row: conv }">
                      <el-image
                        v-if="conv.background_image"
                        :src="conv.background_image"
                        :preview-src-list="[conv.background_image]"
                        :initial-index="0"
                        preview-teleported
                        fit="cover"
                        class="bg-thumb"
                        hide-on-click-modal
                      />
                      <span v-else>-</span>
                    </template>
                  </el-table-column>
                  <!-- 对话内设置的 AI / 用户头像：这两个字段与用户表上的全局头像
                       不同，是本对话独有的设置，排查「用户看到的头像不对」时必需 -->
                  <el-table-column :label="t('AI头像', 'AI Avatar')" width="90" align="center">
                    <template #default="{ row: conv }">
                      <el-image
                        v-if="conv.ai_avatar"
                        :src="conv.ai_avatar"
                        :preview-src-list="[conv.ai_avatar]"
                        :initial-index="0"
                        preview-teleported
                        fit="cover"
                        class="bg-thumb"
                        hide-on-click-modal
                      />
                      <span v-else>-</span>
                    </template>
                  </el-table-column>
                  <el-table-column :label="t('用户头像', 'User Avatar')" width="90" align="center">
                    <template #default="{ row: conv }">
                      <el-image
                        v-if="conv.user_avatar"
                        :src="conv.user_avatar"
                        :preview-src-list="[conv.user_avatar]"
                        :initial-index="0"
                        preview-teleported
                        fit="cover"
                        class="bg-thumb"
                        hide-on-click-modal
                      />
                      <span v-else>-</span>
                    </template>
                  </el-table-column>
                  <el-table-column :label="t('更新时间', 'Updated')" width="150">
                    <template #default="{ row: conv }">{{ formatTime(conv.updated_at) }}</template>
                  </el-table-column>
                  <el-table-column :label="t('Token', 'Tokens')" width="90" align="center">
                    <template #default="{ row: conv }">{{ formatCount(conv.total_tokens) }}</template>
                  </el-table-column>
                  <el-table-column :label="t('操作', 'Actions')" width="120" align="center">
                    <template #default="{ row: conv }">
                      <div class="mp-actions">
                        <el-tooltip :content="t('查看消息记录', 'View messages')" placement="top">
                          <el-button size="small" type="primary" plain :icon="View" @click.stop="viewConversation(conv)" />
                        </el-tooltip>
                        <el-tooltip :content="t('导出 Markdown', 'Export as Markdown')" placement="top">
                          <el-button size="small" plain :icon="Download" @click.stop="exportConversation(conv)" />
                        </el-tooltip>
                        <el-tooltip :content="t('删除对话', 'Delete conversation')" placement="top">
                          <el-button size="small" type="danger" plain :icon="Delete" @click.stop="deleteConversation(conv)" />
                        </el-tooltip>
                      </div>
                    </template>
                  </el-table-column>
                  </el-table>
                </div>
                <div v-if="(row._convPages || 0) > 1" class="batch-bar">
                  <span class="batch-hint">
                    {{ t('共', 'Total') }} {{ row._convTotal || 0 }} {{ t('条对话', 'conversations') }}
                  </span>
                  <el-pagination
                    small
                    layout="prev, pager, next"
                    :current-page="row._convPage || 1"
                    :page-size="20"
                    :total="row._convTotal || 0"
                    @current-change="(p) => loadConversationPage(row, p)"
                  />
                </div>
                <!-- 批量清理：只允许勾选「已移除」的对话（消息已被用户删除，数据库里是残留） -->
                <div v-if="removedConvsOf(row).length" class="batch-bar">
                  <span class="batch-hint">
                    {{ t('该用户有', 'This user has') }} {{ removedConvsOf(row).length }}
                    {{ t('条已移除的对话', 'removed conversations') }}
                  </span>
                  <div class="batch-actions">
                    <el-button size="small" plain @click="selectAllRemoved(row)">
                      {{ t('全选已移除', 'Select all removed') }}
                    </el-button>
                    <el-button size="small" plain @click="clearConvSelection(row)">
                      {{ t('取消选择', 'Clear') }}
                    </el-button>
                    <el-button
                      size="small"
                      type="danger"
                      :disabled="!selectedConvIds[row.id]?.length || batchDeleting"
                      :loading="batchDeleting"
                      @click="batchDeleteRemoved(row)"
                    >
                      {{ t('批量删除', 'Delete selected') }}
                      <template v-if="selectedConvIds[row.id]?.length">
                        ({{ selectedConvIds[row.id].length }})
                      </template>
                    </el-button>
                  </div>
                </div>
                <div v-if="!row._conversations || row._conversations.length === 0" class="col-empty-inner">{{ t('该用户暂无对话', 'No conversations') }}</div>
              </template>
            </el-table-column>

            <el-table-column prop="username" :label="t('用户名', 'Username')" min-width="110" show-overflow-tooltip />
            <el-table-column :label="t('头像', 'Avatar')" width="90" align="center">
              <template #default="{ row }">
                <div class="avatar-cell">
                  <el-image
                    v-if="row.avatar"
                    :src="row.avatar"
                    :preview-src-list="avatarPreviewList(row)"
                    :initial-index="0"
                    preview-teleported
                    fit="cover"
                    class="avatar-thumb"
                    hide-on-click-modal
                  />
                  <span v-else class="avatar-thumb avatar-fallback">{{ (row.username || '?').charAt(0).toUpperCase() }}</span>
                  <el-image
                    v-if="row.ai_avatar"
                    :src="row.ai_avatar"
                    :preview-src-list="avatarPreviewList(row)"
                    :initial-index="row.avatar ? 1 : 0"
                    preview-teleported
                    fit="cover"
                    class="avatar-thumb avatar-ai"
                    hide-on-click-modal
                  />
                </div>
              </template>
            </el-table-column>
            <el-table-column prop="email" :label="t('邮箱', 'Email')" min-width="160" show-overflow-tooltip />
            <el-table-column prop="gender" :label="t('性别', 'Gender')" width="80" align="center">
              <template #default="{ row }">{{ row.gender || '-' }}</template>
            </el-table-column>
            <el-table-column :label="t('状态', 'Status')" width="80" align="center">
              <template #default="{ row }">
                <el-tag :type="row.is_active && !row.deleted_at ? 'success' : 'danger'" size="small">
                  {{ row.deleted_at ? t('已注销', 'Deleted') : (row.is_active ? t('正常', 'Active') : t('停用', 'Disabled')) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="conversation_count" :label="t('对话', 'Chats')" width="80" align="center" />
            <el-table-column prop="message_count" :label="t('消息', 'Msgs')" width="80" align="center" />
            <el-table-column prop="provider_count" :label="t('模型配置', 'Cfgs')" width="90" align="center" />
            <el-table-column prop="persona_count" :label="t('角色', 'Personas')" width="80" align="center" />
            <el-table-column :label="t('Token', 'Tokens')" width="95" align="center">
              <template #default="{ row }">{{ formatCount(row.total_tokens) }}</template>
            </el-table-column>
            <el-table-column :label="t('最近活跃', 'Last Active')" width="150">
              <template #default="{ row }">{{ row.last_active ? formatTime(row.last_active) : '-' }}</template>
            </el-table-column>
            <el-table-column :label="t('注册时间', 'Registered')" width="150">
              <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
            </el-table-column>
            <el-table-column :label="t('操作', 'Actions')" width="90" align="center" fixed="right">
              <template #default="{ row }">
                <el-button size="small" type="primary" plain @click.stop="openUserDetail(row)">
                  {{ t('详情', 'Detail') }}
                </el-button>
              </template>
            </el-table-column>
          </el-table>
          <el-pagination
            v-if="userTotal > 0"
            v-model:current-page="userPage"
            :page-size="userPerPage"
            :total="userTotal"
            layout="total, prev, pager, next"
            class="pl-pagination"
            @current-change="() => loadUsers({ keepSelection: true })"
          />
        </el-tab-pane>

        <!-- 用户反馈 Tab -->
        <el-tab-pane :label="t('用户反馈', 'Feedback')" name="feedback">
          <div class="admin-toolbar">
            <span class="admin-title">{{ t('用户反馈', 'User Feedback') }}</span>
            <el-button size="small" :icon="Refresh" @click="loadFeedback">{{ t('刷新', 'Refresh') }}</el-button>
          </div>

          <el-table :data="feedbackList" v-loading="feedbackLoading" class="admin-table">
            <el-table-column :label="t('反馈人', 'User')" min-width="140">
              <template #default="{ row }">
                <div class="feedback-user">
                  <el-avatar :size="28" :src="row.user?.avatar">
                    {{ row.user?.username?.charAt(0)?.toUpperCase() }}
                  </el-avatar>
                  <div class="feedback-user-meta">
                    <span class="feedback-username">{{ row.user?.username }}</span>
                    <span class="feedback-email">{{ row.user?.email }}</span>
                  </div>
                </div>
              </template>
            </el-table-column>
            <el-table-column :label="t('性别', 'Gender')" width="80" align="center">
              <template #default="{ row }">{{ row.user?.gender || '-' }}</template>
            </el-table-column>
            <el-table-column :label="t('反馈内容', 'Content')" min-width="260">
              <template #default="{ row }">
                <div class="feedback-content-cell" @click="openFeedbackDetail(row)" :title="t('点击查看完整内容', 'Click to view full content')">
                  <span class="feedback-content-text">{{ row.content }}</span>
                </div>
              </template>
            </el-table-column>
            <el-table-column :label="t('允许邮件联系', 'Allow Email')" width="120" align="center">
              <template #default="{ row }">
                <el-tag :type="row.allow_email_contact ? 'success' : 'info'" size="small" effect="plain">
                  {{ row.allow_email_contact ? t('是', 'Yes') : t('否', 'No') }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="contact_email" :label="t('联系邮箱', 'Contact Email')" min-width="160" show-overflow-tooltip />
            <el-table-column :label="t('提交时间', 'Submitted')" width="150">
              <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
            </el-table-column>
          </el-table>

          <div v-if="feedbackTotal > feedbackPageSize" class="lp-pagination">
            <el-pagination
              v-model:current-page="feedbackPage"
              :page-size="feedbackPageSize"
              :total="feedbackTotal"
              layout="prev, pager, next"
              small
              background
              @current-change="loadFeedback"
            />
          </div>
        </el-tab-pane>

        <!-- 卡片广场 Tab -->
        <el-tab-pane :label="t('卡片广场', 'Card Marketplace')" name="marketplace">
          <div class="admin-toolbar">
            <span class="admin-title">{{ t('卡片广场管理', 'Marketplace Management') }}</span>
            <el-button size="small" :icon="Refresh" @click="loadMarketplaceCards">{{ t('刷新', 'Refresh') }}</el-button>
          </div>

          <!-- 筛选：关键词（创建者用户名/邮箱）+ 人物卡性别 + 创建者性别，均走服务端 -->
          <div class="filter-panel">
            <el-input
              v-model="mpFilters.keyword"
              :placeholder="t('创建者用户名 / 邮箱', 'Creator username or email')"
              size="small"
              clearable
              class="filter-input"
              @input="applyMpFilters"
            />
            <el-select
              v-model="mpFilters.gender"
              :placeholder="t('人物卡性别', 'Persona gender')"
              clearable
              size="small"
              class="filter-select"
              @change="applyMpFilters"
            >
              <el-option label="男" value="男" />
              <el-option label="女" value="女" />
              <el-option label="非二元" value="非二元" />
            </el-select>
            <el-select
              v-model="mpFilters.creatorGender"
              :placeholder="t('创建者性别', 'Creator gender')"
              clearable
              size="small"
              class="filter-select"
              @change="applyMpFilters"
            >
              <el-option label="男" value="男" />
              <el-option label="女" value="女" />
              <el-option label="神秘" value="神秘" />
            </el-select>
            <el-button size="small" plain @click="resetMpFilters">{{ t('重置', 'Reset') }}</el-button>
            <span class="filter-count">{{ t('命中', 'Matched') }} {{ mpTotal }}</span>
          </div>

          <el-table :data="mpCards" v-loading="mpLoading" class="admin-table">
            <el-table-column :label="t('头像', 'Avatar')" width="70" align="center">
              <template #default="{ row }">
                <el-image
                  v-if="row.avatar"
                  :src="row.avatar"
                  :preview-src-list="[row.avatar]"
                  preview-teleported
                  fit="cover"
                  class="avatar-thumb"
                  hide-on-click-modal
                />
                <el-avatar v-else :size="36">{{ row.name?.charAt(0) }}</el-avatar>
              </template>
            </el-table-column>
            <el-table-column prop="name" :label="t('名称', 'Name')" min-width="120" show-overflow-tooltip />
            <el-table-column :label="t('性别', 'Gender')" width="90" align="center">
              <template #default="{ row }">{{ row.gender_tag || (row.gender || '-') }}</template>
            </el-table-column>
            <el-table-column prop="description" :label="t('描述', 'Description')" min-width="180" show-overflow-tooltip />
            <el-table-column prop="author_username" :label="t('创建者', 'Creator')" width="120" show-overflow-tooltip />
            <el-table-column :label="t('创建者性别', 'Creator gender')" width="100" align="center">
              <template #default="{ row }">{{ row.author_gender || '-' }}</template>
            </el-table-column>
            <el-table-column prop="author_email" :label="t('邮箱', 'Email')" width="180" show-overflow-tooltip />
            <el-table-column :label="t('点赞/踩', 'Likes')" width="100" align="center">
              <template #default="{ row }">{{ row.likes }} / {{ row.dislikes }}</template>
            </el-table-column>
            <el-table-column :label="t('评论数', 'Comments')" width="80" align="center">
              <template #default="{ row }">{{ row.comment_count }}</template>
            </el-table-column>
            <el-table-column :label="t('发布时间', 'Created')" width="150">
              <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
            </el-table-column>
            <el-table-column :label="t('操作', 'Actions')" width="120" align="center" fixed="right">
              <template #default="{ row }">
                <div class="mp-actions">
                  <el-tooltip :content="t('查看卡片', 'View card')" placement="top">
                    <el-button size="small" type="primary" plain :icon="View" @click="previewMpCard(row)" />
                  </el-tooltip>
                  <el-tooltip :content="t('编辑卡片', 'Edit card')" placement="top">
                    <el-button size="small" type="warning" plain :icon="Edit" @click="openMpEdit(row)" />
                  </el-tooltip>
                  <el-tooltip :content="t('删除', 'Delete')" placement="top">
                    <el-button size="small" type="danger" plain :icon="Delete" @click="deleteMpCard(row)" />
                  </el-tooltip>
                </div>
              </template>
            </el-table-column>
          </el-table>
          <div v-if="mpTotal > mpPageSize" class="pl-pagination">
            <el-pagination
              small
              layout="prev, pager, next, total"
              :current-page="mpPage"
              :page-size="mpPageSize"
              :total="mpTotal"
              @current-change="loadMarketplaceCards"
            />
          </div>
        </el-tab-pane>

        <el-tab-pane :label="t('提示词记录', 'Prompt Tool Logs')" name="promptLogs">
          <div class="admin-toolbar pl-toolbar">
            <div class="admin-title pl-title">
              <span class="pl-title-icon"><el-icon><Document /></el-icon></span>
              <span>{{ t('提示词工具使用记录', 'Prompt Tool Usage') }}</span>
              <span v-if="plTotal > 0" class="pl-title-count">{{ plTotal }}</span>
            </div>
            <div class="toolbar-actions">
              <el-button
                size="small"
                type="danger"
                :icon="Delete"
                :disabled="!plSelected.length"
                @click="deletePromptLogs"
              >
                {{ t('删除选中', 'Delete Selected') }} ({{ plSelected.length }})
              </el-button>
              <el-button size="small" :icon="Refresh" @click="loadPromptLogs">{{ t('刷新', 'Refresh') }}</el-button>
            </div>
          </div>

          <div class="filter-panel pl-filter">
            <el-input
              v-model="plFilters.userId"
              :placeholder="t('按用户 ID 筛选', 'Filter by user ID')"
              size="small"
              clearable
              class="filter-input"
              @input="applyPlFilters"
            >
              <template #prefix><el-icon><Search /></el-icon></template>
            </el-input>
            <el-select
              v-model="plFilters.category"
              :placeholder="t('类型', 'Category')"
              clearable
              size="small"
              class="filter-select"
              @change="applyPlFilters"
            >
              <el-option :label="t('人物设定', 'Character')" value="character" />
              <el-option :label="t('生图/改图', 'Image')" value="image" />
            </el-select>
          </div>

          <div class="pl-table-card">
            <el-table
              :data="promptLogs"
              v-loading="plLoading"
              size="small"
              stripe
              class="pl-table"
              @selection-change="onPlSelectionChange"
            >
              <el-table-column type="selection" width="44" />
              <el-table-column prop="id" label="ID" width="64" align="center" />
              <el-table-column prop="username" :label="t('用户', 'User')" min-width="100" show-overflow-tooltip />
              <el-table-column prop="email" :label="t('邮箱', 'Email')" min-width="150" show-overflow-tooltip />
              <el-table-column :label="t('类型', 'Type')" width="104" align="center">
                <template #default="{ row }">
                  <span class="pl-type-pill" :class="row.category === 'image' ? 'is-image' : 'is-character'">
                    {{ row.category_label }}
                  </span>
                </template>
              </el-table-column>
              <el-table-column :label="t('模型', 'Model')" min-width="140" show-overflow-tooltip>
                <template #default="{ row }">
                  <span class="pl-model-tag">{{ row.model || '-' }}</span>
                </template>
              </el-table-column>
              <el-table-column :label="t('自定义提示词', 'Custom prompt')" width="104" align="center">
                <template #default="{ row }">
                  <el-tag v-if="row.has_custom_prompt" type="warning" size="small" effect="light">{{ t('有', 'Yes') }}</el-tag>
                  <span v-else class="pl-muted">-</span>
                </template>
              </el-table-column>
              <!-- 内容列不设固定宽度：用 min-width 吃掉表格剩余空间，避免右侧留白 -->
              <el-table-column :label="t('内容', 'Content')" min-width="220">
                <template #default="{ row }">
                  <span class="pl-content-cell">{{ row.base_info || row.custom_prompt || row.result }}</span>
                </template>
              </el-table-column>
              <el-table-column :label="t('操作', 'Actions')" width="124" align="center" fixed="right">
                <template #default="{ row }">
                  <div class="pl-actions">
                    <el-tooltip :content="t('查看详情', 'View detail')" placement="top">
                      <el-button size="small" type="primary" plain :icon="View" @click="viewPlRow(row)" />
                    </el-tooltip>
                    <el-tooltip :content="t('删除该记录', 'Delete this record')" placement="top">
                      <el-button size="small" type="danger" plain :icon="Delete" @click="deletePlRow(row)" />
                    </el-tooltip>
                  </div>
                </template>
              </el-table-column>
              <el-table-column :label="t('时间', 'Time')" width="150">
                <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
              </el-table-column>
            </el-table>
          </div>

          <el-pagination
            v-if="plTotal > 0"
            v-model:current-page="plPage"
            :page-size="plPerPage"
            :total="plTotal"
            layout="total, prev, pager, next"
            @current-change="loadPromptLogs"
            class="pl-pagination"
          />
        </el-tab-pane>

        <el-tab-pane :label="t('对话素材记录', 'Media History')" name="mediaLogs">
          <div class="admin-toolbar">
            <span class="admin-title">{{ t('对话素材设置历史', 'Conversation Media History') }}</span>
            <el-button size="small" type="danger" :disabled="!mediaSelected.length" :icon="Delete" @click="deleteMediaLogs">
              {{ t('删除选中', 'Delete Selected') }} ({{ mediaSelected.length }})
            </el-button>
            <el-button size="small" :icon="Refresh" @click="loadMediaLogs">{{ t('刷新', 'Refresh') }}</el-button>
          </div>
          <div class="filter-panel">
            <el-input
              v-model="mediaFilters.userId"
              :placeholder="t('按用户 ID 筛选', 'Filter by user ID')"
              size="small"
              clearable
              class="filter-input"
              @input="applyMediaFilters"
            />
            <el-select
              v-model="mediaFilters.mediaType"
              :placeholder="t('类型', 'Type')"
              clearable
              size="small"
              class="filter-select"
              @change="applyMediaFilters"
            >
              <el-option :label="t('对话背景图', 'Conv Background')" value="background" />
              <el-option :label="t('对话AI头像', 'Conv AI Avatar')" value="ai_avatar" />
              <el-option :label="t('对话用户头像', 'Conv User Avatar')" value="user_avatar" />
              <el-option :label="t('系统背景图', 'System Background')" value="profile_background" />
              <el-option :label="t('系统用户头像', 'System User Avatar')" value="profile_avatar" />
              <el-option :label="t('系统AI头像', 'System AI Avatar')" value="profile_ai_avatar" />
              <el-option :label="t('上传图片', 'Uploaded Image')" value="upload" />
            </el-select>
          </div>

          <el-table :data="mediaLogs" v-loading="mediaLoading" size="small" stripe @selection-change="onMediaSelectionChange">
            <el-table-column type="selection" width="44" />
            <el-table-column prop="id" label="ID" width="60" align="center" />
            <el-table-column prop="username" :label="t('用户', 'User')" width="100" show-overflow-tooltip />
            <el-table-column :label="t('归属', 'Scope')" width="130" show-overflow-tooltip>
              <template #default="{ row }">
                <!-- 系统级素材（系统设置的头像/背景、聊天上传的图片）没有归属对话 -->
                <span v-if="!row.conversation_id" class="media-scope-global">{{ t('系统', 'System') }}</span>
                <span v-else>{{ row.conversation_title || `#${row.conversation_id}` }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="media_type_label" :label="t('类型', 'Type')" width="110" align="center" />
            <el-table-column :label="t('预览', 'Preview')" width="64" align="center">
              <template #default="{ row }">
                <!-- preview-teleported + hide-on-click-modal：预览层挂到 body 且点遮罩即关，
                     不会像默认 viewer 那样全屏压住后台，点完还能继续操作表格 -->
                <el-image
                  :src="row.value"
                  fit="cover"
                  class="media-thumb"
                  :preview-src-list="[row.value]"
                  :initial-index="0"
                  preview-teleported
                  hide-on-click-modal
                  :z-index="3000"
                />
              </template>
            </el-table-column>
            <el-table-column :label="t('来源', 'Source')" min-width="140" show-overflow-tooltip>
              <template #default="{ row }">
                <span class="media-value-preview">{{ row.value }}</span>
              </template>
            </el-table-column>
            <el-table-column :label="t('时间', 'Time')" width="150">
              <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
            </el-table-column>
            <el-table-column :label="t('操作', 'Actions')" width="80" align="center" fixed="right">
              <template #default="{ row }">
                <el-tooltip :content="t('删除该记录', 'Delete this record')" placement="top">
                  <el-button size="small" type="danger" plain :icon="Delete" @click="deleteMediaLog(row)" />
                </el-tooltip>
              </template>
            </el-table-column>
          </el-table>
          <el-pagination
            v-if="mediaTotal > 0"
            v-model:current-page="mediaPage"
            :page-size="mediaPerPage"
            :total="mediaTotal"
            layout="total, prev, pager, next"
            @current-change="loadMediaLogs"
            style="margin-top: 12px; justify-content: flex-end"
          />
        </el-tab-pane>
        <el-tab-pane :label="t('匿名反馈会话', 'Support Chat')" name="supportChats">
          <div class="admin-toolbar support-toolbar">
            <span class="admin-title">{{ t('匿名反馈会话', 'Anonymous Support Chats') }}</span>
            <el-button size="small" :icon="Refresh" @click="loadSupportChats">{{ t('刷新反馈', 'Refresh chats') }}</el-button>
          </div>
          <el-table :data="supportChats" v-loading="supportChatsLoading" size="small" stripe class="admin-table support-table">
            <el-table-column prop="user.id" label="UID" width="70" align="center" />
            <el-table-column prop="anonymous_id" :label="t('匿名ID', 'Anonymous ID')" width="130" />
            <el-table-column :label="t('用户信息', 'User')" min-width="180">
              <template #default="{ row }">{{ row.user?.username }} · {{ row.user?.email }}</template>
            </el-table-column>
            <el-table-column :label="t('最近消息', 'Last message')" min-width="200" show-overflow-tooltip>
              <template #default="{ row }">{{ row.last_message?.content || '-' }}</template>
            </el-table-column>
            <el-table-column :label="t('未读', 'Unread')" width="70" align="center">
              <template #default="{ row }"><el-badge v-if="row.admin_unread" :value="row.admin_unread" /></template>
            </el-table-column>
            <el-table-column :label="t('时间', 'Time')" width="150">
              <template #default="{ row }">{{ formatTime(row.last_message_at) }}</template>
            </el-table-column>
            <el-table-column :label="t('操作', 'Actions')" width="90" align="center">
              <template #default="{ row }"><el-button size="small" type="primary" plain @click="openSupportChat(row)">{{ t('回复', 'Reply') }}</el-button></template>
            </el-table-column>
          </el-table>

        </el-tab-pane>

      </el-tabs>

      <!-- 管理员编辑广场卡片 -->
      <el-dialog
        v-model="mpEditVisible"
        :title="t('编辑卡片', 'Edit Card')"
        width="min(520px, 94vw)"
        append-to-body
        destroy-on-close
      >
        <el-form :model="mpEditForm" label-position="top">
          <el-form-item :label="t('名称', 'Name')" required>
            <el-input v-model="mpEditForm.name" maxlength="100" />
          </el-form-item>
          <el-form-item :label="t('描述', 'Description')" required>
            <el-input v-model="mpEditForm.description" type="textarea" :rows="2" maxlength="100" resize="none" />
          </el-form-item>
          <el-form-item :label="t('类型', 'Type')">
            <el-input v-model="mpEditForm.gender" maxlength="20" :placeholder="t('男 / 女 / 神秘 / 自定义', 'Male / Female / Custom')" />
          </el-form-item>
          <el-form-item :label="t('人设提示词', 'Character Prompt')" required>
            <el-input v-model="mpEditForm.system_prompt" type="textarea" :rows="6" maxlength="50000" resize="none" />
          </el-form-item>
          <el-form-item :label="t('开场白', 'Greeting')" required>
            <el-input v-model="mpEditForm.greeting" type="textarea" :rows="3" maxlength="100" resize="none" />
          </el-form-item>
          <el-form-item :label="t('头像 URL', 'Avatar URL')">
            <el-input v-model="mpEditForm.avatar" :placeholder="t('留空则不修改', 'Leave empty to keep')" />
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="mpEditVisible = false">{{ t('取消', 'Cancel') }}</el-button>
          <el-button type="primary" :loading="mpEditSaving" @click="saveMpEdit">
            {{ t('保存', 'Save') }}
          </el-button>
        </template>
      </el-dialog>

      <!-- 提示词记录详情 -->
      <el-dialog
        v-model="plDetailVisible"
        :title="t('使用详情', 'Usage Detail')"
        width="min(880px, 94vw)"
        append-to-body
      >
        <div v-if="plDetail" class="pl-detail">
          <div class="pl-meta-bar">
            <div class="pl-meta-item">
              <span class="pl-meta-key">{{ t('用户', 'User') }}</span>
              <span class="pl-meta-val">{{ plDetail.username }} <i class="pl-meta-sub">{{ plDetail.email }}</i></span>
            </div>
            <div class="pl-meta-item">
              <span class="pl-meta-key">{{ t('类型', 'Type') }}</span>
              <span class="pl-meta-val">{{ plDetail.category_label }}</span>
            </div>
            <div class="pl-meta-item">
              <span class="pl-meta-key">{{ t('模型', 'Model') }}</span>
              <span class="pl-meta-val">{{ plDetail.model || '-' }}</span>
            </div>
            <div class="pl-meta-item">
              <span class="pl-meta-key">{{ t('时间', 'Time') }}</span>
              <span class="pl-meta-val">{{ formatTime(plDetail.created_at) }}</span>
            </div>
          </div>
          <div class="pl-detail-block">
            <div class="pl-detail-label"><span class="pl-dot is-warn"></span>{{ t('自定义提示词', 'Custom prompt') }}</div>
            <pre class="pl-detail-text">{{ plDetail.custom_prompt || t('（未使用自定义，使用系统默认）', '(none — system default used)') }}</pre>
          </div>
          <div class="pl-detail-block">
            <div class="pl-detail-label"><span class="pl-dot"></span>{{ t('基础信息', 'Base info') }}</div>
            <pre class="pl-detail-text">{{ plDetail.base_info || t('（未填写）', '(empty)') }}</pre>
          </div>
          <div class="pl-detail-block">
            <div class="pl-detail-label"><span class="pl-dot is-brand"></span>{{ t('生成结果', 'Generated result') }}</div>
            <pre class="pl-detail-text">{{ plDetail.result }}</pre>
          </div>
        </div>
        <template #footer>
          <el-button @click="plDetailVisible = false">{{ t('关闭', 'Close') }}</el-button>
          <el-button type="danger" :icon="Delete" @click="deletePlRow(plDetail)">
            {{ t('删除该记录', 'Delete this record') }}
          </el-button>
        </template>
      </el-dialog>
    </main>

    <!-- 人设详情模态框 -->
    <el-dialog v-model="personaDetailVisible" :title="personaDetailData?.persona_name" width="min(520px, 90vw)" align-center>
      <div v-if="personaDetailData" class="persona-detail-modal">
        <div class="pdm-row">
          <el-image
            v-if="personaDetailData.persona_avatar"
            :src="personaDetailData.persona_avatar"
            :preview-src-list="[personaDetailData.persona_avatar]"
            preview-teleported
            fit="cover"
            class="pdm-avatar"
            hide-on-click-modal
          />
          <el-avatar v-else :size="64">{{ personaDetailData.persona_name?.charAt(0) }}</el-avatar>
          <div class="pdm-info">
            <h3>
              {{ personaDetailData.persona_name }}
              <el-tag size="small" effect="plain" :type="personaDetailData.persona_kind === 'user' ? 'warning' : 'primary'">
                {{ personaDetailData.persona_kind === 'user' ? t('用户人设', 'User Persona') : t('AI人设', 'AI Persona') }}
              </el-tag>
            </h3>
            <p>{{ personaDetailData.persona_description || t('暂无简介', 'No description') }}</p>
          </div>
        </div>
        <div v-if="personaDetailData.persona_system_prompt" class="pdm-section">
          <div class="pdm-label">{{ t('人设提示词', 'System Prompt') }}</div>
          <div class="pdm-box">{{ personaDetailData.persona_system_prompt }}</div>
        </div>
        <div v-if="personaDetailData.persona_user_prompt" class="pdm-section">
          <div class="pdm-label">{{ t('玩家设定', 'Player Persona') }}</div>
          <div class="pdm-box">{{ personaDetailData.persona_user_prompt }}</div>
        </div>
        <div v-if="personaDetailData.persona_greeting" class="pdm-section">
          <div class="pdm-label">{{ t('开场白', 'Greeting') }}</div>
          <div class="pdm-box">{{ personaDetailData.persona_greeting }}</div>
        </div>

        <!-- 对话中设置的用户人设（表格不再单列，在弹窗内一并展示） -->
        <template v-if="personaDetailData.user_persona">
          <el-divider content-position="left">
            <el-tag size="small" effect="plain" type="warning">{{ t('对话中的用户人设', 'User Persona in Chat') }}</el-tag>
          </el-divider>
          <div class="pdm-row">
            <el-image
              v-if="personaDetailData.user_persona.avatar"
              :src="personaDetailData.user_persona.avatar"
              :preview-src-list="[personaDetailData.user_persona.avatar]"
              preview-teleported
              fit="cover"
              class="pdm-avatar"
              hide-on-click-modal
            />
            <div class="pdm-info">
              <h3>{{ personaDetailData.user_persona.name }}</h3>
              <p>{{ personaDetailData.user_persona.description || t('暂无简介', 'No description') }}</p>
            </div>
          </div>
          <div v-if="personaDetailData.user_persona.user_prompt" class="pdm-section">
            <div class="pdm-label">{{ t('玩家设定', 'Player Persona') }}</div>
            <div class="pdm-box">{{ personaDetailData.user_persona.user_prompt }}</div>
          </div>
          <div v-if="personaDetailData.user_persona.greeting" class="pdm-section">
            <div class="pdm-label">{{ t('开场白', 'Greeting') }}</div>
            <div class="pdm-box">{{ personaDetailData.user_persona.greeting }}</div>
          </div>
        </template>
      </div>
    </el-dialog>

    <!-- 用户详情：人设、Token 用量和模型配置 -->
    <el-dialog
      v-model="userDetailVisible"
      :title="userDetailUser ? `${userDetailUser.username} · ${userDetailUser.email}` : t('用户详情', 'User Detail')"
      width="min(920px, 94vw)"
      align-center
    >
      <div v-loading="userDetailLoading" class="user-detail">
        <el-tabs v-model="userDetailTab">
          <el-tab-pane :label="t('概览', 'Overview')" name="overview">
            <el-descriptions v-if="userDetailSummary" :column="2" border>
              <el-descriptions-item :label="t('用户 ID', 'User ID')">{{ userDetailSummary.id }}</el-descriptions-item>
              <el-descriptions-item :label="t('状态', 'Status')">{{ userDetailSummary.is_active ? t('正常', 'Active') : t('停用', 'Disabled') }}</el-descriptions-item>
              <el-descriptions-item :label="t('注册时间', 'Registered')">{{ formatTime(userDetailSummary.created_at) }}</el-descriptions-item>
              <el-descriptions-item :label="t('最近登录', 'Last login')">{{ formatTime(userDetailSummary.last_login_at) }}</el-descriptions-item>
              <el-descriptions-item :label="t('最近聊天', 'Last chat')">{{ formatTime(userDetailSummary.last_chat_at || userDetailSummary.last_message_at) }}</el-descriptions-item>
              <el-descriptions-item :label="t('对话数', 'Conversations')">{{ userDetailSummary.conversation_count }}</el-descriptions-item>
              <el-descriptions-item :label="t('消息数', 'Messages')">{{ userDetailSummary.message_count }}</el-descriptions-item>
              <el-descriptions-item :label="t('人物卡', 'Personas')">{{ userDetailSummary.persona_count }}</el-descriptions-item>
              <el-descriptions-item :label="t('模型配置', 'Providers')">{{ userDetailSummary.provider_count }}</el-descriptions-item>
              <el-descriptions-item :label="t('总 Token', 'Total tokens')">{{ formatCount(userDetailSummary.total_tokens) }}</el-descriptions-item>
              <el-descriptions-item :label="t('输入 Token', 'Prompt tokens')">{{ formatCount(userDetailSummary.prompt_tokens) }}</el-descriptions-item>
              <el-descriptions-item :label="t('输出 Token', 'Completion tokens')">{{ formatCount(userDetailSummary.completion_tokens) }}</el-descriptions-item>
              <el-descriptions-item :label="t('缓存命中', 'Cached tokens')">{{ formatCount(userDetailSummary.cached_tokens) }}</el-descriptions-item>
              <el-descriptions-item :label="t('剩余免费生图', 'Free images')">{{ userDetailSummary.free_images_remaining ?? '-' }}</el-descriptions-item>
            </el-descriptions>
          </el-tab-pane>

          <el-tab-pane :label="`${t('人物卡', 'Personas')} (${userDetailPersonas.length})`" name="personas">
            <el-empty v-if="!userDetailPersonas.length" :description="t('暂无人物卡', 'No personas')" />
            <template v-else>
              <div v-if="selectedPersonaIds.length" class="batch-bar" style="margin-bottom: 10px;">
                <span class="batch-hint">{{ t('已选', 'Selected') }} {{ selectedPersonaIds.length }} {{ t('项', 'items') }}</span>
                <div class="batch-actions">
                  <el-button size="small" plain @click="selectedPersonaIds = []">{{ t('取消选择', 'Clear') }}</el-button>
                  <el-button size="small" type="danger" :loading="batchDeletingPersonas" @click="batchDeletePersonas">
                    {{ t('批量删除', 'Delete selected') }} ({{ selectedPersonaIds.length }})
                  </el-button>
                </div>
              </div>
              <el-table :data="userDetailPersonas" size="small" class="admin-table" @selection-change="onPersonaSelectChange">
                <el-table-column type="selection" width="42" />
                <el-table-column prop="name" :label="t('名称', 'Name')" min-width="120" show-overflow-tooltip />
                <el-table-column :label="t('类型', 'Type')" width="90">
                  <template #default="{ row }">
                    <el-tag size="small" effect="plain">{{ row.persona_type === 'user' ? t('用户', 'User') : t('AI', 'AI') }}</el-tag>
                  </template>
                </el-table-column>
                <el-table-column :label="t('世界书', 'Worldbook')" width="80" align="center">
                  <template #default="{ row }">{{ row.worldbook_count || 0 }}</template>
                </el-table-column>
                <el-table-column :label="t('操作', 'Actions')" width="100" align="center">
                  <template #default="{ row }">
                    <el-button size="small" text type="primary" @click="showPersonaDetailFromList(row)">{{ t('查看', 'View') }}</el-button>
                  </template>
                </el-table-column>
              </el-table>
              <!-- 展开详情区 -->
              <el-collapse v-model="expandedPersonaIds" style="margin-top: 10px;">
                <el-collapse-item v-for="p in userDetailPersonas" :key="p.id" :name="p.id">
                  <template #title>
                    <span style="font-size: 12px; color: var(--text-muted);">{{ p.name }} - {{ t('点击展开详情', 'Click to expand') }}</span>
                  </template>
                  <div class="pl-detail-block">
                    <div class="pl-detail-label">{{ t('AI 提示词', 'System prompt') }}</div>
                    <pre class="pl-detail-text">{{ p.system_prompt || '-' }}</pre>
                  </div>
                  <div class="pl-detail-block">
                    <div class="pl-detail-label">{{ t('玩家设定', 'Player persona') }}</div>
                    <pre class="pl-detail-text">{{ p.user_prompt || '-' }}</pre>
                  </div>
                  <div v-if="p.greeting" class="pl-detail-block">
                    <div class="pl-detail-label">{{ t('开场白', 'Greeting') }}</div>
                    <pre class="pl-detail-text">{{ p.greeting }}</pre>
                  </div>
                </el-collapse-item>
              </el-collapse>
            </template>
          </el-tab-pane>

          <el-tab-pane :label="t('Token 用量', 'Token Usage')" name="usage">
            <template v-if="userDetailUsage">
              <div class="usage-cards">
                <div class="usage-card"><b>{{ formatCount(userDetailUsage.totals.total_tokens) }}</b><span>{{ t('总 Token', 'Total') }}</span></div>
                <div class="usage-card"><b>{{ formatCount(userDetailUsage.totals.prompt_tokens) }}</b><span>{{ t('输入', 'Prompt') }}</span></div>
                <div class="usage-card"><b>{{ formatCount(userDetailUsage.totals.completion_tokens) }}</b><span>{{ t('输出', 'Completion') }}</span></div>
                <div class="usage-card"><b>{{ formatCount(userDetailUsage.totals.cached_tokens) }}</b><span>{{ t('缓存命中', 'Cached') }}</span></div>
              </div>
              <div class="detail-subtitle">{{ t('按模型', 'By model') }}</div>
              <el-table :data="userDetailUsage.by_model" size="small" class="admin-table">
                <el-table-column prop="model" :label="t('模型', 'Model')" min-width="160" show-overflow-tooltip />
                <el-table-column :label="t('总 Token', 'Tokens')" width="100"><template #default="{ row }">{{ formatCount(row.total_tokens) }}</template></el-table-column>
                <el-table-column :label="t('缓存', 'Cached')" width="90"><template #default="{ row }">{{ formatCount(row.cached_tokens) }}</template></el-table-column>
                <el-table-column prop="message_count" :label="t('消息数', 'Msgs')" width="80" align="center" />
              </el-table>
            </template>
          </el-tab-pane>

          <el-tab-pane :label="`${t('模型配置', 'Providers')} (${userDetailProviders.length})`" name="providers">
            <el-empty v-if="!userDetailProviders.length" :description="t('暂无模型配置', 'No providers')" />
            <el-table v-else :data="userDetailProviders" size="small" class="admin-table">
              <el-table-column prop="name" :label="t('名称', 'Name')" min-width="130" show-overflow-tooltip />
              <el-table-column prop="brand" :label="t('品牌', 'Brand')" width="100" />
              <el-table-column prop="api_url" :label="t('接口地址', 'API URL')" min-width="220" show-overflow-tooltip />
              <el-table-column prop="api_key_masked" :label="t('API Key', 'API Key')" width="130" />
              <el-table-column :label="t('模型数', 'Models')" width="80" align="center">
                <template #default="{ row }">{{ row.models?.length || 0 }}</template>
              </el-table-column>
            </el-table>
          </el-tab-pane>
        </el-tabs>
      </div>
    </el-dialog>

    <!-- 对话消息记录抽屉 -->
    <el-drawer
      v-model="msgDrawerVisible"
      :title="t('对话记录', 'Conversation Messages')"
      size="min(560px, 92vw)"
      direction="rtl"
    >
      <div ref="msgDrawerBodyRef" class="msg-drawer" v-loading="msgDrawerLoading">
        <div v-if="msgDrawerData.conversation" class="md-head">
          <div class="md-title">{{ msgDrawerData.conversation.title || t('(无标题)', '(Untitled)') }}</div>
          <div class="md-meta">
            <el-tag size="small" effect="plain">{{ t('共', 'Total') }} {{ msgDrawerData.total || msgDrawerData.messages.length }} {{ t('条', 'msgs') }}</el-tag>
            <el-tag v-if="msgDrawerData.conversation.username" size="small" effect="plain" type="info">
              {{ msgDrawerData.conversation.username }}
            </el-tag>
            <el-tag v-if="msgDrawerData.conversation.deleted_at" size="small" effect="plain" type="warning">
              {{ t('用户已移除该对话', 'Removed by user') }}
            </el-tag>
            <el-button size="small" plain :icon="Refresh" @click="refreshConversationMessages">
              {{ t('刷新最新', 'Refresh latest') }}
            </el-button>
          </div>
        </div>

        <div v-if="msgDrawerData.hasMore" class="md-load-more">
          <el-button size="small" plain :loading="msgDrawerLoading" @click="loadOlderMessages">
            {{ t('加载更早消息', 'Load older messages') }}
          </el-button>
        </div>

        <div v-if="!msgDrawerLoading && msgDrawerData.messages.length === 0" class="md-empty">
          {{ t('该对话暂无消息', 'No messages yet') }}
        </div>

        <div v-for="m in msgDrawerData.messages" :key="m.id" class="md-msg" :class="m.role">
          <div class="md-msg-head">
            <span class="md-role">{{ roleLabel(m.role) }}</span>
            <span class="md-time">{{ formatTime(m.created_at) }}</span>
          </div>
          <div v-if="m.model || m.total_tokens" class="md-msg-meta">
            <span v-if="m.model">{{ m.model }}</span>
            <span v-if="m.total_tokens">
              {{ t('消耗', 'Used') }} {{ formatCount(m.total_tokens) }} tokens
              <template v-if="m.prompt_tokens != null"> · 输入 {{ formatCount(m.prompt_tokens) }}</template>
              <template v-if="m.completion_tokens != null"> · 输出 {{ formatCount(m.completion_tokens) }}</template>
              <template v-if="m.cached_tokens"> · 缓存 {{ formatCount(m.cached_tokens) }}</template>
            </span>
          </div>
          <div class="md-content">{{ m.content }}</div>
          <div v-if="m.reasoning_content" class="md-reasoning">{{ m.reasoning_content }}</div>
          <el-image
            v-if="m.image_url"
            :src="m.image_url"
            :preview-src-list="msgDrawerData.messages.filter(x => x.image_url).map(x => x.image_url)"
            :initial-index="msgDrawerData.messages.filter(x => x.image_url).findIndex(x => x.id === m.id)"
            preview-teleported
            fit="contain"
            class="md-image"
            hide-on-click-modal
          />
        </div>
      </div>
    </el-drawer>

    <el-dialog
      v-model="supportDialogVisible"
      :title="t('匿名反馈会话', 'Anonymous Support Chat')"
      width="min(680px, 96vw)"
      align-center
      class="support-admin-dialog"
      @opened="scrollSupportToLatest(true)"
    >
      <div v-loading="supportDialogLoading" class="support-admin-chat">
        <div class="support-admin-user">
          <strong>{{ supportDetail.user?.username || '-' }}</strong>
          <span>{{ supportDetail.user?.email || '-' }}</span>
          <el-tag size="small" effect="plain">{{ supportDetail.user?.id || '-' }}</el-tag>
        </div>
        <div ref="supportAdminMessagesRef" class="support-admin-messages">
          <div v-for="m in supportDetail.messages" :key="m.id" class="support-admin-msg" :class="m.sender">
            <div>{{ m.content }}</div>
            <el-image v-if="m.image_url" :src="m.image_url" fit="contain" class="support-admin-image" @load="scrollSupportToLatest(true)" />
            <time>{{ formatTime(m.created_at) }}<template v-if="m.sender === 'admin'"> · {{ m.read_by_user ? t('已读', 'Read') : t('未读', 'Unread') }}</template></time>
          </div>
        </div>
        <div class="support-admin-reply">
          <el-upload :show-file-list="false" :before-upload="uploadSupportReplyImage" accept="image/*">
            <el-button circle plain :icon="Picture" />
          </el-upload>
          <el-input
            v-model="supportReply"
            type="textarea"
            :autosize="{ minRows: 2, maxRows: 6 }"
            resize="none"
            maxlength="2000"
            :placeholder="t('输入回复内容，Enter 发送，Shift+Enter 换行（可附带图片）', 'Write a reply. Enter to send, Shift+Enter for a new line (image optional)')"
            @keydown="handleSupportReplyKeydown"
          />
          <el-button type="primary" :disabled="!canReplySupport" :loading="supportReplying" @click="replySupport">{{ t('发送回复', 'Send reply') }}</el-button>
        </div>
        <div v-if="supportReplyImage" class="support-admin-image-preview"><el-image :src="supportReplyImage" fit="contain" /></div>
      </div>
    </el-dialog>

    <!-- 卡片广场详情弹窗（管理员查看完整信息） -->
    <el-dialog
      v-model="mpDetailVisible"
      :title="t('卡片详情', 'Card Details')"
      width="min(560px, 92vw)"
      align-center
      destroy-on-close
      class="mp-detail-dialog"
    >
      <div v-if="mpDetailData" v-loading="mpDetailLoading" class="mp-detail-body">
        <div class="mp-detail-head">
          <el-image
            v-if="mpDetailData.avatar"
            :src="mpDetailData.avatar"
            :preview-src-list="[mpDetailData.avatar]"
            preview-teleported
            fit="cover"
            class="mp-detail-avatar"
            hide-on-click-modal
          />
          <el-avatar v-else :size="80">{{ mpDetailData.name?.charAt(0) }}</el-avatar>
          <div class="mp-detail-meta">
            <h3 class="mp-detail-name">{{ mpDetailData.name }}</h3>
            <div class="mp-detail-tags">
              <el-tag size="small" effect="plain">{{ mpDetailData.gender_tag || (mpDetailData.gender || '-') }}</el-tag>
              <el-tag size="small" type="info" effect="plain">{{ mpDetailData.author_username }}</el-tag>
              <el-tag size="small" type="warning" effect="plain" v-if="mpDetailData.author_gender">
                {{ t('创建者', 'Creator') }} {{ mpDetailData.author_gender }}
              </el-tag>
            </div>
            <div class="mp-detail-stats">
              <span class="mp-stat like"><ThumbIcon :size="14" /> {{ formatCount(mpDetailData.likes || 0) }}</span>
              <span class="mp-stat dislike"><ThumbIcon :size="14" down /> {{ formatCount(mpDetailData.dislikes || 0) }}</span>
              <span class="mp-stat comment"><el-icon><ChatLineRound /></el-icon> {{ formatCount(mpDetailData.comment_count || 0) }}</span>
            </div>
          </div>
        </div>
        <p class="mp-detail-desc">{{ mpDetailData.description }}</p>
        <div v-if="mpDetailData.greeting" class="mp-detail-section">
          <div class="mp-detail-label">{{ t('开场白', 'Greeting') }}</div>
          <div class="mp-detail-box mp-detail-greeting">{{ mpDetailData.greeting }}</div>
        </div>
        <div class="mp-detail-section">
          <div class="mp-detail-label">{{ t('人设提示词', 'System Prompt') }}</div>
          <div class="mp-detail-box mp-detail-prompt">{{ mpDetailData.system_prompt }}</div>
        </div>

        <!-- 评论区：管理员可见真实用户名 -->
        <div class="mp-detail-section mp-comments-section">
          <div class="mp-detail-label">
            {{ t('评论', 'Comments') }} ({{ (mpDetailData.comments || []).length }})
          </div>
          <div v-if="(mpDetailData.comments || []).length === 0" class="mp-no-comments">
            {{ t('暂无评论', 'No comments yet') }}
          </div>
          <div v-else class="mp-comments-list">
            <div v-for="c in mpDetailData.comments" :key="c.id" class="mp-comment">
              <div class="mp-comment-head">
                <span class="mp-comment-user">{{ c.username || t('未知用户', 'Unknown') }}</span>
                <span class="mp-comment-time">{{ formatTime(c.created_at) }}</span>
              </div>
              <p class="mp-comment-text">{{ c.content }}</p>
            </div>
          </div>
        </div>
      </div>
    </el-dialog>
    <!-- 反馈详情弹窗 -->
    <el-dialog
      v-model="feedbackDetailVisible"
      :title="t('反馈详情', 'Feedback Detail')"
      width="min(560px, 94vw)"
      align-center
      class="feedback-detail-dialog"
    >
      <div v-if="feedbackDetail" class="fb-detail">
        <div class="fb-detail-user">
          <el-avatar :size="42" :src="feedbackDetail.user?.avatar">
            {{ feedbackDetail.user?.username?.charAt(0)?.toUpperCase() }}
          </el-avatar>
          <div class="fb-detail-user-meta">
            <span class="fb-detail-username">{{ feedbackDetail.user?.username }}</span>
            <span class="fb-detail-email">{{ feedbackDetail.user?.email }}</span>
          </div>
          <el-tag size="small" effect="plain">
            {{ t('性别', 'Gender') }} {{ feedbackDetail.user?.gender || '-' }}
          </el-tag>
        </div>

        <div class="fb-detail-row">
          <span class="fb-detail-label">{{ t('提交时间', 'Submitted') }}</span>
          <span>{{ formatTime(feedbackDetail.created_at) }}</span>
        </div>
        <div class="fb-detail-row">
          <span class="fb-detail-label">{{ t('允许邮件联系', 'Allow Email') }}</span>
          <el-tag :type="feedbackDetail.allow_email_contact ? 'success' : 'info'" size="small" effect="plain">
            {{ feedbackDetail.allow_email_contact ? t('是', 'Yes') : t('否', 'No') }}
          </el-tag>
        </div>
        <div class="fb-detail-row" v-if="feedbackDetail.allow_email_contact">
          <span class="fb-detail-label">{{ t('联系邮箱', 'Contact Email') }}</span>
          <span class="fb-detail-contact">{{ feedbackDetail.contact_email || '-' }}</span>
        </div>

        <div class="fb-detail-content">
          <div class="fb-detail-label">{{ t('反馈内容', 'Content') }}</div>
          <div class="fb-detail-text">{{ feedbackDetail.content }}</div>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh, Back, SwitchButton, Monitor, View, Download, Delete, Edit, ChatLineRound, Document, Search, Picture, User, Lock } from '@element-plus/icons-vue'
import { adminApi, resAi, uploadApi, ensureAdminSession } from '@/utils/resAi'
import logger from '@/utils/logger'
import { t } from '../i18n'
import ThumbIcon from '../components/ThumbIcon.vue'
import brandIcon from '@/assets/icon/ChatBotIcon.png'

const router = useRouter()
const adminName = ref(localStorage.getItem('admin_username') || '')
// 管理后台唯一入口 /chatbotadmin：未登录时展示内嵌登录页，不再跳转独立 /admin 路由。
// 登录态与普通用户同一套：access 7 天 + refresh 30 天，启动时静默续期，不用每次登录。
const authed = ref(!!localStorage.getItem('admin_token'))
const loginUsername = ref('')
const loginPassword = ref('')
const loginLoading = ref(false)

async function doLogin() {
  if (!loginUsername.value.trim() || !loginPassword.value) {
    ElMessage.warning(t('请输入管理员账号和密码', 'Enter admin username and password'))
    return
  }
  loginLoading.value = true
  try {
    // adminApi.login 内部已把 access / refresh 两个令牌写进 localStorage
    const res = await adminApi.login(loginUsername.value.trim(), loginPassword.value)
    if (res.code === 200) {
      localStorage.setItem('admin_username', res.data.username)
      adminName.value = res.data.username
      authed.value = true
      ElMessage.success(t('登录成功', 'Signed in'))
      loadAll()
    } else {
      ElMessage.error(res.message || t('登录失败', 'Login failed'))
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.message || e.message || t('登录失败', 'Login failed'))
  } finally {
    loginLoading.value = false
  }
}

const stats = ref({})
const users = ref([])
const statsLoading = ref(false)
const usersLoading = ref(false)
const allUsers = ref([])
const userPage = ref(1)
const userPerPage = ref(50)
const userTotal = ref(0)
const userPages = ref(0)
const userSort = ref('created_at')
const userOrder = ref('desc')
const userTableRef = ref(null)
let userFilterTimer = null
// 当前展开的用户 id 集合：刷新列表后据此恢复展开状态，避免展开区白屏
const expandedUserIds = ref(new Set())
// 每个用户展开区里被勾选的对话 id（key = userId）：仅允许勾选「已移除」的对话
const selectedConvIds = ref({})
const batchDeleting = ref(false)
// 内层对话表格 ref：批量勾选/取消时同步表格选中状态
const convTableRef = ref(null)
const activeTab = ref('users')

// 人物卡批量选择与删除
const selectedPersonaIds = ref([])
const batchDeletingPersonas = ref(false)
const expandedPersonaIds = ref([])

// 混合筛选条件（每个条件都可单独使用，也可任意叠加）
const emptyFilters = () => ({
  keyword: '',
  genders: [],
  statuses: [],
  activity: '',
  hasConfig: [],
})
const filters = ref(emptyFilters())

// 卡片广场
const mpCards = ref([])
const mpLoading = ref(false)
const mpTotal = ref(0)
const mpPage = ref(1)
const mpPageSize = ref(50)
const mpLoaded = ref(false)
const mpFilters = ref({
  keyword: '',
  gender: '', // 人物卡性别：男 / 女 / 非二元
  creatorGender: '', // 创建者（用户）性别：男 / 女 / 神秘
})

// 用户反馈
const feedbackList = ref([])
const feedbackLoading = ref(false)
const feedbackPage = ref(1)
const feedbackPageSize = ref(20)
const feedbackTotal = ref(0)
const feedbackDetailVisible = ref(false)
const feedbackDetail = ref(null)

function openFeedbackDetail(row) {
  feedbackDetail.value = row
  feedbackDetailVisible.value = true
}

// 管理员卡片详情弹窗状态（复用公共详情接口，无需额外后端）
const mpDetailVisible = ref(false)
const mpDetailLoading = ref(false)
const mpDetailData = ref(null)

// 筛选变化 → 回到第一页重新请求（筛选条件全部由服务端执行）
function applyMpFilters() {
  mpPage.value = 1
  loadMarketplaceCards(1)
}

function resetMpFilters() {
  mpFilters.value = { keyword: '', gender: '', creatorGender: '' }
  applyMpFilters()
}

// 人设详情模态框
const personaDetailVisible = ref(false)
const personaDetailData = ref(null)

// 对话消息抽屉
const msgDrawerVisible = ref(false)
const msgDrawerLoading = ref(false)
const msgDrawerData = ref({ conversation: null, messages: [] })
const msgDrawerBodyRef = ref(null)

// 用户详情
const userDetailVisible = ref(false)
const userDetailLoading = ref(false)
const userDetailTab = ref('overview')
const userDetailUser = ref(null)
const userDetailSummary = ref(null)
const userDetailPersonas = ref([])
const userDetailProviders = ref([])
const userDetailUsage = ref(null)

function avatarPreviewList(row) {
  return [row.avatar, row.ai_avatar].filter(Boolean)
}

function roleLabel(role) {
  return { user: t('用户', 'User'), assistant: t('AI', 'AI'), system: t('系统', 'System') }[role] || role
}

function _startOfToday() {
  const d = new Date()
  d.setHours(0, 0, 0, 0)
  return d.getTime()
}

function applyFilters() {
  userPage.value = 1
  clearTimeout(userFilterTimer)
  userFilterTimer = setTimeout(() => loadUsers(), 300)
}

function resetFilters() {
  filters.value = emptyFilters()
  applyFilters()
}

function onUserSortChange() {
  userPage.value = 1
  loadUsers({ keepSelection: true })
}

function formatTime(iso) {
  if (!iso) return '-'
  const d = new Date(iso)
  if (isNaN(d.getTime())) return iso
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).format(d)
}

// 千位 k 计数：1000 -> 1k，1500 -> 1.5k，10000 -> 10k，百万及以上用 m
function formatCount(n) {
  const v = Number(n) || 0
  if (v < 1000) return String(v)
  if (v < 1000000) {
    const k = v / 1000
    return (k >= 100 ? Math.round(k) : Math.round(k * 10) / 10) + 'k'
  }
  const m = v / 1000000
  return (m >= 100 ? Math.round(m) : Math.round(m * 10) / 10) + 'm'
}

async function loadStats() {
  statsLoading.value = true
  try {
    const res = await adminApi.stats()
    if (res.code === 200) stats.value = res.data
  } catch (e) {
    ElMessage.error(t('加载统计失败', 'Failed to load stats'))
  } finally {
    statsLoading.value = false
  }
}

async function loadUsers(opts = {}) {
  usersLoading.value = true
  try {
    const res = await adminApi.users({
      page: userPage.value,
      perPage: userPerPage.value,
      keyword: (filters.value.keyword || '').trim(),
      genders: filters.value.genders,
      statuses: filters.value.statuses,
      hasConfig: filters.value.hasConfig,
      activity: filters.value.activity,
      sort: userSort.value,
      order: userOrder.value,
    })
    if (res.code === 200) {
      const payload = res.data
      const list = Array.isArray(payload) ? payload : (payload?.items || [])
      userTotal.value = Array.isArray(payload) ? list.length : (payload?.total || 0)
      userPages.value = Array.isArray(payload) ? 1 : (payload?.pages || 0)
      userPage.value = Array.isArray(payload) ? 1 : (payload?.page || userPage.value)
      // 关键：不能整体替换行对象。el-table 以 row 对象身份维护展开状态
      //（expandedRows.includes(row)），换成新对象会让所有展开行失效，
      // 表现为「刷新后展开区白屏」。这里按 id 复用旧行对象，保留
      // _conversations / _loading，从而保住展开状态与已加载的对话数据。
      const oldById = new Map(allUsers.value.map(u => [u.id, u]))
      allUsers.value = list.map(u => {
        const old = oldById.get(u.id)
        return old ? Object.assign(old, u) : { ...u, _conversations: null, _loading: false }
      })
      users.value = allUsers.value
      if (!opts.keepSelection) {
        // 普通刷新：清空已勾选的对话（行数据可能已变），下次展开重新勾选
        selectedConvIds.value = {}
      }
      await restoreExpandedRows()
    } else if (res.code === 403) {
      ElMessage.warning(t('无管理员权限', 'No admin permission'))
    }
  } catch (e) {
    ElMessage.error(t('加载用户失败', 'Failed to load users'))
  } finally {
    usersLoading.value = false
  }
}

// 刷新用户列表后恢复此前的展开行，并按需补载尚未取过的对话数据
async function restoreExpandedRows() {
  const table = userTableRef.value
  if (!table) return
  const expanded = expandedUserIds.value
  if (!expanded.size) return
  for (const row of users.value) {
    if (!expanded.has(row.id)) continue
    table.toggleRowExpansion(row, true)
    if (!row._conversations) {
      loadConversations(row)
    }
  }
}

async function loadConversations(user, page = 1, force = false) {
  if (user._conversations && !force && user._convPage === page) return
  user._loading = true
  try {
    const res = await adminApi.userConversations(user.id, {
      page,
      perPage: 20,
      sort: 'updated_at',
      order: 'desc',
    })
    if (res.code === 200) {
      const payload = res.data || {}
      const items = Array.isArray(payload) ? payload : (payload.items || [])
      user._conversations = items.map(c => ({ ...c }))
      user._convPage = Array.isArray(payload) ? 1 : (payload.page || page)
      user._convPages = Array.isArray(payload) ? 1 : (payload.pages || 0)
      user._convTotal = Array.isArray(payload) ? items.length : (payload.total || 0)
    }
  } catch (e) {
    ElMessage.error(t('加载对话失败', 'Failed to load conversations'))
  } finally {
    user._loading = false
  }
}

function loadConversationPage(user, page) {
  loadConversations(user, page, true)
}

// 外层用户表展开时加载该用户对话（修复展开无数据 bug）
// 同时记录展开状态，供列表刷新后恢复（见 restoreExpandedRows）
function onUserExpand(row, expandedRows) {
  const isExpanded = expandedRows && expandedRows.includes(row)
  if (isExpanded) {
    expandedUserIds.value.add(row.id)
    loadConversations(row, row._convPage || 1)
  } else {
    expandedUserIds.value.delete(row.id)
  }
}

// ---- 批量删除「已移除」的对话 ----
// 用户的删除是软删除（deleted_at），数据库里仍残留对话行；后台可批量真删清理。
// 只允许勾选 exists=false 的行，避免误删用户仍在使用的对话。
function canSelectConv(conv) {
  return conv && conv.exists === false
}

function removedConvsOf(row) {
  return (row._conversations || []).filter(c => c.exists === false)
}

function onConvSelectChange(row, selection) {
  const next = { ...selectedConvIds.value }
  next[row.id] = (selection || []).filter(c => canSelectConv(c)).map(c => c.id)
  selectedConvIds.value = next
}

function selectAllRemoved(row) {
  const ids = removedConvsOf(row).map(c => c.id)
  const next = { ...selectedConvIds.value }
  next[row.id] = ids
  selectedConvIds.value = next
  // 同步表格勾选状态（逐行 toggleRowSelection，nextTick 等表格渲染完）
  nextTick(() => {
    const table = convTableRef.value
    if (!table) return
    for (const conv of row._conversations || []) {
      table.toggleRowSelection(conv, ids.includes(conv.id))
    }
  })
}

function clearConvSelection(row) {
  const next = { ...selectedConvIds.value }
  next[row.id] = []
  selectedConvIds.value = next
  nextTick(() => {
    const table = convTableRef.value
    if (!table) return
    for (const conv of row._conversations || []) {
      table.toggleRowSelection(conv, false)
    }
  })
}

async function batchDeleteRemoved(row) {
  const ids = selectedConvIds.value[row.id] || []
  if (!ids.length) return
  try {
    await ElMessageBox.confirm(
      t(`确定彻底删除选中的 ${ids.length} 条已移除对话及其全部消息吗？该操作不可恢复。`,
        `Permanently delete ${ids.length} selected removed conversation(s) and all their messages? This cannot be undone.`),
      t('确认删除', 'Confirm delete'),
      { type: 'warning', confirmButtonText: t('删除', 'Delete'), cancelButtonText: t('取消', 'Cancel') }
    )
  } catch (e) {
    return // 用户取消
  }

  batchDeleting.value = true
  try {
    const res = await adminApi.batchDeleteConversations(ids)
    if (res.code === 200) {
      ElMessage.success(res.message || t('删除成功', 'Deleted'))
      clearConvSelection(row)
      // 重新拉取该用户的对话列表 + 后台统计（对话数会变）
      row._conversations = null
      await Promise.all([loadConversations(row), loadStats(), loadUsers({ keepSelection: true })])
    }
  } catch (e) {
    ElMessage.error(t('批量删除失败', 'Batch delete failed'))
  } finally {
    batchDeleting.value = false
  }
}

// ---- 人物卡批量选择与删除 ----
function onPersonaSelectChange(selection) {
  selectedPersonaIds.value = (selection || []).map(p => p.id)
}

async function batchDeletePersonas() {
  const ids = selectedPersonaIds.value
  if (!ids.length) return
  try {
    await ElMessageBox.confirm(
      t(`确定彻底删除选中的 ${ids.length} 个人物卡吗？该操作不可恢复。`,
        `Permanently delete ${ids.length} selected persona(s)? This cannot be undone.`),
      t('确认删除', 'Confirm delete'),
      { type: 'warning', confirmButtonText: t('删除', 'Delete'), cancelButtonText: t('取消', 'Cancel') }
    )
  } catch (e) {
    return // 用户取消
  }

  batchDeletingPersonas.value = true
  try {
    const res = await adminApi.batchDeletePersonas(ids)
    if (res.code === 200) {
      ElMessage.success(res.message || t('删除成功', 'Deleted'))
      selectedPersonaIds.value = []
      // 重新拉取人物卡列表和统计
      await Promise.all([loadUserDetailPersonas(), loadStats()])
    }
  } catch (e) {
    ElMessage.error(t('批量删除失败', 'Batch delete failed'))
  } finally {
    batchDeletingPersonas.value = false
  }
}

async function exportConversation(conv) {
  try {
    await adminApi.exportConversation(conv.id)
    ElMessage.success(t(`已导出「${conv.title}」`, `Exported "${conv.title}"`))
  } catch (e) {
    ElMessage.error(t('导出失败', 'Export failed') + `：${e.message || ''}`)
  }
}

// 点击「消息数」或「查看」直接查看该对话的完整消息记录
function _msgDrawerScrollEl() {
  return msgDrawerBodyRef.value?.closest('.el-drawer__body') || null
}

async function _scrollMessageDrawerToBottom() {
  await nextTick()
  const el = _msgDrawerScrollEl()
  if (el) el.scrollTop = el.scrollHeight
}

async function _scrollMessageDrawerToTop() {
  await nextTick()
  const el = _msgDrawerScrollEl()
  if (el) el.scrollTop = 0
}

async function viewConversation(conv) {
  msgDrawerData.value = {
    conversation: { id: conv.id, title: conv.title },
    messages: [],
    total: conv.message_count || 0,
    hasMore: false,
    nextBeforeId: null,
  }
  msgDrawerVisible.value = true
  msgDrawerLoading.value = true
  try {
    const res = await adminApi.conversationMessages(conv.id, { limit: 100 })
    if (res.code === 200) {
      msgDrawerData.value = {
        conversation: res.data.conversation || { id: conv.id, title: conv.title },
        messages: res.data.messages || [],
        total: res.data.total || 0,
        hasMore: !!res.data.has_more,
        nextBeforeId: res.data.next_before_id || null,
      }
    }
  } catch (e) {
    ElMessage.error(t('加载消息失败', 'Failed to load messages'))
  } finally {
    msgDrawerLoading.value = false
    await _scrollMessageDrawerToTop()
  }
}

async function loadOlderMessages() {
  const current = msgDrawerData.value
  if (msgDrawerLoading.value || !current.hasMore || !current.nextBeforeId) return
  const scrollEl = _msgDrawerScrollEl()
  const prevHeight = scrollEl?.scrollHeight || 0
  const prevTop = scrollEl?.scrollTop || 0
  msgDrawerLoading.value = true
  try {
    const res = await adminApi.conversationMessages(current.conversation.id, {
      limit: 100,
      beforeId: current.nextBeforeId,
    })
    if (res.code !== 200) return
    const existing = new Set(current.messages.map(m => m.id))
    const older = (res.data.messages || []).filter(m => !existing.has(m.id))
    current.messages = [...older, ...current.messages]
    current.hasMore = !!res.data.has_more
    current.nextBeforeId = res.data.next_before_id || null
    current.total = res.data.total || current.total
    await nextTick()
    if (scrollEl) scrollEl.scrollTop = scrollEl.scrollHeight - prevHeight + prevTop
  } catch (e) {
    ElMessage.error(t('加载更早消息失败', 'Failed to load older messages'))
  } finally {
    msgDrawerLoading.value = false
  }
}

async function refreshConversationMessages() {
  const current = msgDrawerData.value
  if (!current.conversation?.id || msgDrawerLoading.value) return
  msgDrawerLoading.value = true
  try {
    const res = await adminApi.conversationMessages(current.conversation.id, { limit: 100 })
    if (res.code !== 200) return
    msgDrawerData.value = {
      conversation: res.data.conversation || current.conversation,
      messages: res.data.messages || [],
      total: res.data.total || 0,
      hasMore: !!res.data.has_more,
      nextBeforeId: res.data.next_before_id || null,
    }
    await _scrollMessageDrawerToBottom()
  } catch (e) {
    ElMessage.error(t('刷新消息失败', 'Failed to refresh messages'))
  } finally {
    msgDrawerLoading.value = false
  }
}

async function deleteConversation(conv) {
  try {
    await ElMessageBox.confirm(
      t(`确定彻底删除对话「${conv.title}」及其全部消息吗？该操作不可恢复。`,
        `Permanently delete "${conv.title}" and all its messages? This cannot be undone.`),
      t('确认删除', 'Confirm delete'),
      { type: 'warning', confirmButtonText: t('删除', 'Delete'), cancelButtonText: t('取消', 'Cancel') }
    )
  } catch (e) {
    return // 用户取消
  }
  try {
    const res = await adminApi.deleteConversation(conv.id)
    if (res.code === 200) {
      ElMessage.success(t('已删除', 'Deleted'))
      // 从当前展开的列表里移除，并刷新统计
      const owner = allUsers.value.find(u => Array.isArray(u._conversations) && u._conversations.some(c => c.id === conv.id))
      if (owner) {
        owner._conversations = owner._conversations.filter(c => c.id !== conv.id)
        owner.conversation_count = Math.max(0, (owner.conversation_count || 0) - 1)
        owner.message_count = Math.max(0, (owner.message_count || 0) - (conv.message_count || 0))
      }
      loadStats()
    }
  } catch (e) {
    ElMessage.error(t('删除失败', 'Delete failed') + `：${e.message || ''}`)
  }
}

async function loadFeedback() {
  feedbackLoading.value = true
  try {
    const res = await adminApi.feedbackList(feedbackPage.value, feedbackPageSize.value)
    if (res.code === 200) {
      feedbackList.value = res.data.items || []
      feedbackTotal.value = res.data.total || 0
    }
  } catch (e) {
    ElMessage.error(t('加载反馈失败', 'Failed to load feedback'))
  } finally {
    feedbackLoading.value = false
  }
}

async function loadMarketplaceCards(page = 1) {
  mpLoading.value = true
  mpPage.value = page
  try {
    // 服务端分页 + 服务端筛选：不再一次性拉全量再前端过滤
    const res = await adminApi.marketplaceCards(page, {
      keyword: mpFilters.value.keyword,
      gender: mpFilters.value.gender,
      creator_gender: mpFilters.value.creatorGender,
    })
    if (res.code === 200) {
      const data = res.data || {}
      mpCards.value = data.items || []
      mpTotal.value = data.total || 0
      mpLoaded.value = true
    } else {
      ElMessage.warning(t('加载卡片失败', 'Failed to load cards'))
    }
  } catch (e) {
    ElMessage.error(t('加载卡片失败', 'Failed to load cards'))
  } finally {
    mpLoading.value = false
  }
}

// 查看卡片详情：拉取完整数据（含 system_prompt / greeting / 评论区真实用户名）并打开弹窗
// ========== 管理员编辑广场卡片 ==========
const mpEditVisible = ref(false)
const mpEditSaving = ref(false)
const mpEditForm = reactive({ id: null, name: '', description: '', gender: '', system_prompt: '', greeting: '', avatar: '' })

// 列表接口不返回 system_prompt（体积大），打开编辑时按需拉完整详情
async function openMpEdit(card) {
  if (!card) return
  Object.assign(mpEditForm, {
    id: card.id,
    name: card.name || '',
    description: card.description || '',
    gender: card.gender || '',
    system_prompt: '',
    greeting: '',
    avatar: card.avatar || '',
  })
  mpEditVisible.value = true
  try {
    const res = await adminApi.marketplaceCardDetail(card.id)
    if (res.code === 200) {
      mpEditForm.system_prompt = res.data.system_prompt || ''
      mpEditForm.greeting = res.data.greeting || ''
    }
  } catch (e) {
    ElMessage.warning(t('读取提示词失败，可直接重写', 'Failed to load prompt; you may retype it'))
  }
}

async function saveMpEdit() {
  mpEditSaving.value = true
  try {
    const payload = {
      name: mpEditForm.name.trim(),
      description: mpEditForm.description.trim(),
      gender: mpEditForm.gender.trim(),
      system_prompt: mpEditForm.system_prompt.trim(),
      greeting: mpEditForm.greeting.trim(),
    }
    // 头像留空表示不修改，避免误清
    if (mpEditForm.avatar.trim()) payload.avatar = mpEditForm.avatar.trim()
    const res = await adminApi.updateMarketplaceCard(mpEditForm.id, payload)
    if (res.code === 200) {
      ElMessage.success(t('已保存', 'Saved'))
      mpEditVisible.value = false
      loadMarketplaceCards()
    } else {
      ElMessage.warning(res.message || t('保存失败', 'Save failed'))
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.message || t('保存失败', 'Save failed'))
  } finally {
    mpEditSaving.value = false
  }
}

// ========== 提示词工具使用记录 ==========
const promptLogs = ref([])
const plLoading = ref(false)
const plPage = ref(1)
const plPerPage = 20
const plTotal = ref(0)
const plSelected = ref([])
const plFilters = ref({ userId: '', category: '' })
const plDetailVisible = ref(false)
const plDetail = ref(null)

async function loadPromptLogs() {
  plLoading.value = true
  try {
    const res = await adminApi.promptToolLogs(
      plPage.value, plPerPage,
      plFilters.value.userId.trim(), plFilters.value.category
    )
    if (res.code === 200) {
      promptLogs.value = res.data.items || []
      plTotal.value = res.data.total || 0
    }
  } catch (e) {
    logger.error('加载提示词记录失败', e)
    ElMessage.error(t('加载提示词记录失败', 'Failed to load prompt tool logs'))
  } finally {
    plLoading.value = false
  }
}

function applyPlFilters() {
  plPage.value = 1
  loadPromptLogs()
}

function viewPlRow(row) {
  plDetail.value = row
  plDetailVisible.value = true
}

function onPlSelectionChange(rows) {
  plSelected.value = (rows || []).map(r => r.id)
}

/** 删除当前页最后一条后回退一页，避免停留在空白页 */
function syncPageAfterDelete() {
  if (promptLogs.value.length <= 1 && plPage.value > 1) plPage.value -= 1
  loadPromptLogs()
}

// 删除单条提示词记录（带二次确认，误删审计记录无法恢复）
async function deletePlRow(row) {
  if (!row) return
  try {
    await ElMessageBox.confirm(
      t(`确定删除该条提示词记录（ID ${row.id}）？删除后不可恢复。`, `Delete prompt log #${row.id}? This cannot be undone.`),
      t('确认删除', 'Confirm'),
      { type: 'warning', confirmButtonText: t('删除', 'Delete'), cancelButtonText: t('取消', 'Cancel') }
    )
  } catch (e) {
    return // 用户取消
  }
  try {
    const res = await adminApi.deletePromptToolLog(row.id)
    if (res.code === 200) {
      ElMessage.success(t('已删除该记录', 'Record deleted'))
      // 可能是在详情弹窗里点的，同步关掉，避免停留在已删除记录的详情上
      if (plDetail.value?.id === row.id) {
        plDetailVisible.value = false
        plDetail.value = null
      }
      syncPageAfterDelete()
    } else {
      ElMessage.warning(res.message || t('删除失败', 'Delete failed'))
    }
  } catch (e) {
    logger.error('删除提示词记录失败', e)
    ElMessage.error(t('删除失败', 'Delete failed'))
  }
}

// 批量删除选中的提示词记录
async function deletePromptLogs() {
  if (!plSelected.value.length) return
  try {
    await ElMessageBox.confirm(
      t(`确定删除选中的 ${plSelected.value.length} 条提示词记录？删除后不可恢复。`,
        `Delete ${plSelected.value.length} selected prompt logs? This cannot be undone.`),
      t('确认删除', 'Confirm'),
      { type: 'warning', confirmButtonText: t('删除', 'Delete'), cancelButtonText: t('取消', 'Cancel') }
    )
  } catch (e) {
    return // 用户取消
  }
  try {
    const res = await adminApi.deletePromptToolLogs(plSelected.value)
    if (res.code === 200) {
      ElMessage.success(res.message || t('已删除选中记录', 'Selected records deleted'))
      plSelected.value = []
      loadPromptLogs()
    } else {
      ElMessage.warning(res.message || t('删除失败', 'Delete failed'))
    }
  } catch (e) {
    logger.error('批量删除提示词记录失败', e)
    ElMessage.error(t('删除失败', 'Delete failed'))
  }
}

// ========== 对话素材设置历史 ==========
const mediaLogs = ref([])
const mediaLoading = ref(false)
const supportChats = ref([])
const supportChatsLoading = ref(false)
const supportDialogVisible = ref(false)
const supportDialogLoading = ref(false)
const supportDetail = ref({ thread: null, user: null, messages: [] })
const supportReply = ref('')
const supportReplyImage = ref('')
const supportReplying = ref(false)
const supportAdminMessagesRef = ref(null)
const canReplySupport = computed(() => !!supportReply.value.trim() || !!supportReplyImage.value)
const mediaPage = ref(1)
const mediaPerPage = 20
const mediaTotal = ref(0)
const mediaSelected = ref([])
const mediaFilters = ref({ userId: '', mediaType: '' })

async function loadSupportChats() {
  supportChatsLoading.value = true
  try {
    const res = await adminApi.supportChats()
    if (res.code === 200) supportChats.value = res.data.items || []
  } catch (e) {
    ElMessage.error(t('加载反馈会话失败', 'Failed to load support chats'))
  } finally {
    supportChatsLoading.value = false
  }
}

async function scrollSupportToLatest(force = false) {
  await nextTick()
  const el = supportAdminMessagesRef.value
  if (!el) return
  await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))
  if (force || el.scrollHeight - el.scrollTop - el.clientHeight < 96) {
    el.scrollTop = el.scrollHeight
  }
}

async function openSupportChat(row) {
  supportDialogVisible.value = true
  supportDialogLoading.value = true
  try {
    const res = await adminApi.supportThread(row.id)
    if (res.code === 200) supportDetail.value = res.data
    await scrollSupportToLatest(true)
  } catch (e) {
    ElMessage.error(t('加载会话失败', 'Failed to load thread'))
  } finally {
    supportDialogLoading.value = false
  }
}

async function replySupport() {
  const content = supportReply.value.trim()
  if ((!content && !supportReplyImage.value) || !supportDetail.value.thread?.id || supportReplying.value) return
  supportReplying.value = true
  try {
    const res = await adminApi.replySupportThread(supportDetail.value.thread.id, content, supportReplyImage.value)
    if (res.code === 200) {
      supportReply.value = ''
      supportReplyImage.value = ''
      await openSupportChat({ id: supportDetail.value.thread.id })
    } else {
      ElMessage.warning(res.message || t('回复失败', 'Reply failed'))
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.message || t('回复失败', 'Reply failed'))
  } finally {
    supportReplying.value = false
  }
}

function handleSupportReplyKeydown(event) {
  // 与用户端客服框一致：Enter 发送，Shift+Enter 换行，输入法组合期间不触发
  if (event.key !== 'Enter' || event.shiftKey || event.isComposing) return
  event.preventDefault()
  replySupport()
}

async function uploadSupportReplyImage(file) {
  try {
    const res = await uploadApi.uploadImage(file)
    if (res?.code === 200) supportReplyImage.value = res.data.url
  } catch (e) { ElMessage.error(t('图片上传失败', 'Image upload failed')) }
  return false
}

async function loadMediaLogs() {
  mediaLoading.value = true
  try {
    const res = await adminApi.conversationMediaLogs(
      mediaPage.value, mediaPerPage,
      mediaFilters.value.userId.trim(), mediaFilters.value.mediaType
    )
    if (res.code === 200) {
      mediaLogs.value = res.data.items || []
      mediaTotal.value = res.data.total || 0
    }
  } catch (e) {
    logger.error('加载对话素材历史失败', e)
    ElMessage.error(t('加载对话素材历史失败', 'Failed to load media history'))
  } finally {
    mediaLoading.value = false
  }
}

function applyMediaFilters() {
  mediaPage.value = 1
  loadMediaLogs()
}

function onMediaSelectionChange(rows) {
  mediaSelected.value = (rows || []).map(r => r.id)
}

// 删除单条对话素材记录（带二次确认）
async function deleteMediaLog(row) {
  if (!row) return
  try {
    await ElMessageBox.confirm(
      t(`确定删除该条素材记录（ID ${row.id}）？仅删除历史记录，不影响会话中正在生效的素材。`,
        `Delete media log #${row.id}? Only the history record is removed; the active media is unaffected.`),
      t('确认删除', 'Confirm'),
      { type: 'warning', confirmButtonText: t('删除', 'Delete'), cancelButtonText: t('取消', 'Cancel') }
    )
  } catch (e) {
    return // 用户取消
  }
  try {
    const res = await adminApi.deleteConversationMediaLog(row.id)
    if (res.code === 200) {
      ElMessage.success(t('已删除该记录', 'Record deleted'))
      loadMediaLogs()
    } else {
      ElMessage.warning(res.message || t('删除失败', 'Delete failed'))
    }
  } catch (e) {
    logger.error('删除对话素材记录失败', e)
    ElMessage.error(t('删除失败', 'Delete failed'))
  }
}

async function deleteMediaLogs() {
  if (!mediaSelected.value.length) return
  try {
    await ElMessageBox.confirm(
      t(`确定删除选中的 ${mediaSelected.value.length} 条素材记录？删除后不可恢复。`,
        `Delete ${mediaSelected.value.length} selected media logs? This cannot be undone.`),
      t('确认删除', 'Confirm'),
      { type: 'warning', confirmButtonText: t('删除', 'Delete'), cancelButtonText: t('取消', 'Cancel') }
    )
  } catch (e) {
    return // 用户取消
  }
  try {
    const res = await adminApi.deleteConversationMediaLogs(mediaSelected.value)
    if (res.code === 200) {
      ElMessage.success(res.message || t('已删除选中记录', 'Selected records deleted'))
      mediaSelected.value = []
      loadMediaLogs()
    } else {
      ElMessage.warning(res.message || t('删除失败', 'Delete failed'))
    }
  } catch (e) {
    logger.error('删除对话素材历史失败', e)
    ElMessage.error(t('删除失败', 'Delete failed'))
  }
}

async function previewMpCard(card) {
  if (!card) return
  mpDetailVisible.value = true
  mpDetailLoading.value = true
  // 先把基本信息塞进去，让弹窗立即有内容显示
  mpDetailData.value = card
  try {
    const res = await adminApi.marketplaceCardDetail(card.id)
    if (res.code === 200 && mpDetailData.value?.id === card.id) {
      // 合并后端最新数据（更权威的统计数字）
      mpDetailData.value = { ...card, ...res.data }
    }
  } catch (e) {
    ElMessage.warning(t('加载完整详情失败，仅展示已缓存信息', 'Failed to load full details'))
  } finally {
    mpDetailLoading.value = false
  }
}

async function deleteMpCard(card) {
  try {
    await ElMessageBox.confirm(t(`确定删除卡片「${card.name}」吗？`, `Delete card "${card.name}"?`), t('确认', 'Confirm'), { type: 'warning' })
    const res = await adminApi.deleteMarketplaceCard(card.id)
    if (res.code === 200) {
      ElMessage.success(t('已删除', 'Deleted'))
      loadMarketplaceCards(mpPage.value)
    }
  } catch (e) {
    if (e !== 'cancel') ElMessage.error(t('删除失败', 'Delete failed'))
  }
}

// 旧版「打开新窗口预览头像」已被「弹窗查看完整详情」替代，无需保留。
// 原函数已合并至 previewMpCard 上面那个异步实现。

// kind: 'ai' 对话中的 AI 人设；'user' 对话中设置的用户人设
function showPersonaDetail(conv, kind = 'ai') {
  const name = conv.persona_name
  if (!name) return
  personaDetailData.value = {
    persona_name: name,
    persona_avatar: conv.persona_avatar,
    persona_description: conv.persona_description,
    persona_system_prompt: conv.persona_system_prompt,
    persona_user_prompt: conv.persona_user_prompt,
    persona_greeting: conv.persona_greeting,
    persona_kind: 'ai',
    // 对话中设置的用户人设：表格已去掉该列，统一在弹窗里一并展示
    user_persona: conv.user_persona_name ? {
      name: conv.user_persona_name,
      avatar: conv.user_persona_avatar,
      description: conv.user_persona_description,
      user_prompt: conv.user_persona_user_prompt,
      greeting: conv.user_persona_greeting,
    } : null,
  }
  personaDetailVisible.value = true
}

function showPersonaDetailFromList(persona) {
  personaDetailData.value = {
    persona_name: persona.name,
    persona_avatar: persona.avatar,
    persona_description: persona.description,
    persona_system_prompt: persona.system_prompt,
    persona_user_prompt: persona.user_prompt,
    persona_greeting: persona.greeting,
    persona_kind: persona.persona_type || 'ai',
  }
  personaDetailVisible.value = true
}

async function openUserDetail(row) {
  if (!row) return
  userDetailVisible.value = true
  userDetailLoading.value = true
  userDetailTab.value = 'overview'
  userDetailUser.value = row
  userDetailSummary.value = null
  userDetailPersonas.value = []
  userDetailProviders.value = []
  userDetailUsage.value = null

  const results = await Promise.allSettled([
    adminApi.userSummary(row.id),
    adminApi.userPersonas(row.id),
    adminApi.userProviders(row.id),
    adminApi.userUsage(row.id, 30),
  ])
  if (results[0].status === 'fulfilled' && results[0].value.code === 200) {
    userDetailSummary.value = results[0].value.data
  }
  if (results[1].status === 'fulfilled' && results[1].value.code === 200) {
    userDetailPersonas.value = results[1].value.data.items || []
  }
  if (results[2].status === 'fulfilled' && results[2].value.code === 200) {
    userDetailProviders.value = results[2].value.data.items || []
  }
  if (results[3].status === 'fulfilled' && results[3].value.code === 200) {
    userDetailUsage.value = results[3].value.data
  }
  userDetailLoading.value = false
}

async function loadUserDetailPersonas() {
  if (!userDetailUser.value) return
  try {
    const res = await adminApi.userPersonas(userDetailUser.value.id)
    if (res.code === 200) {
      userDetailPersonas.value = res.data.items || []
    }
  } catch (e) {
    console.error('loadUserDetailPersonas failed', e)
  }
}

async function loadAll() {
  await Promise.all([loadStats(), loadUsers()])
}

function doLogout() {
  ElMessageBox.confirm(
    t('确定要退出管理后台吗？', 'Log out of admin panel?'),
    t('确认', 'Confirm'),
    { type: 'warning' }
  ).then(() => {
    adminApi.logout()
    authed.value = false
  }).catch(() => {})
}

onMounted(async () => {
  // 启动先确保登录态：access 过期但 refresh 还在就静默续期（30 天内不用重新登录）
  await ensureAdminSession()
  // 校验令牌是否仍有效，失效则回到内嵌登录页
  try {
    const res = await adminApi.status()
    if (res.code !== 200) authed.value = false
  } catch (e) {
    // 401 时 adminReq 已尝试续期；到这里仍失败说明 refresh 也过期了
    authed.value = false
  }
  if (authed.value) await loadAll()
})

// 切换到「卡片广场」Tab 时自动加载一次（首次进入也会触发）
watch(activeTab, (val) => {
  if (val === 'marketplace' && !mpLoaded.value && !mpLoading.value) {
    loadMarketplaceCards()
  }
  if (val === 'feedback' && feedbackList.value.length === 0 && !feedbackLoading.value) {
    loadFeedback()
  }
})

// 切换标签页时按需加载：提示词记录首次进入才拉取，避免首屏多余请求
function onTabChange(name) {
  if (name === 'promptLogs') loadPromptLogs()
  if (name === 'mediaLogs') {
    loadMediaLogs()
  }
  if (name === 'supportChats') loadSupportChats()
}
</script>

<style scoped>
.admin-login-page {
  width: 100%;
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #fbf3ea 0%, #f3e3d0 100%);
  padding: 20px;
}
.login-card {
  width: 100%;
  max-width: 400px;
  background: #fff;
  border-radius: 18px;
  box-shadow: 0 12px 36px rgba(120, 84, 56, .16);
  padding: 40px 36px 32px;
  text-align: center;
}
.login-card .brand {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  margin-bottom: 10px;
}
.login-card .brand-img {
  width: 40px;
  height: 40px;
  border-radius: 10px;
}
.login-card .brand-text {
  font-size: 20px;
  font-weight: 700;
  color: var(--text-primary, #4a3b2e);
}
.login-card .subtitle {
  font-size: 12.5px;
  color: var(--text-muted, #9a8b7a);
  margin-bottom: 26px;
  line-height: 1.6;
}
.login-card .login-form {
  text-align: left;
}
.login-card .login-btn {
  width: 100%;
  margin-top: 4px;
}
.login-card .back-link {
  margin-top: 18px;
}
.admin-page {
  height: 100vh;
  height: 100dvh;
  display: flex;
  flex-direction: column;
  background: var(--app-bg, #faf6f1);
  overflow-x: hidden;
  overflow-y: auto;
}

.admin-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 24px;
  background: var(--surface, #fff);
  border-bottom: 1px solid var(--border-color, #e9e0d4);
  flex-wrap: wrap;
}

.header-brand {
  display: flex;
  align-items: center;
  gap: 10px;
}

.brand-img {
  width: 30px;
  height: 30px;
  border-radius: 8px;
  object-fit: cover;
}

.brand-text {
  font-size: 18px;
  font-weight: 700;
  color: #7a4c24;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.admin-name {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
  color: #a9815a;
  margin-right: 6px;
}

.admin-main {
  flex: 1;
  min-height: 0;
  padding: 24px;
  max-width: 1280px;
  width: 100%;
  margin: 0 auto;
  box-sizing: border-box;
}

.admin-stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
  gap: 12px;
  margin-bottom: 20px;
}

.stat-card {
  background: var(--surface, #fff);
  border: 1px solid var(--border-color, #e9e0d4);
  border-radius: 10px;
  padding: 16px 12px;
  text-align: center;
}

.stat-num {
  font-size: 22px;
  font-weight: 700;
  color: #4a3520;
}

.stat-num .sub {
  font-size: 13px;
  color: #a9815a;
}

.stat-label {
  font-size: 12px;
  color: #8a6a48;
  margin-top: 4px;
}

.stat-today {
  background: linear-gradient(135deg, #fbead6, #fff);
}

.admin-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.admin-title {
  font-size: 15px;
  font-weight: 600;
  color: #4a3520;
}

.toolbar-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.admin-table {
  width: 100%;
  background: var(--surface, #fff);
  border-radius: 10px;
}

.inner-table {
  width: calc(100% - 24px);
  min-width: 1320px;
  margin: 8px 12px;
  border: 1px solid var(--border-color, #e9e0d4);
  border-radius: 8px;
}

.inner-table-scroll {
  width: 100%;
  overflow-x: auto;
  overflow-y: auto;
  padding-bottom: 6px;
  scrollbar-gutter: stable;
}

.inner-table-scroll::-webkit-scrollbar {
  height: 9px;
  width: 9px;
}

.inner-table-scroll::-webkit-scrollbar-thumb {
  background: rgba(176, 106, 46, 0.35);
  border-radius: 999px;
}

.msg-panel {
  padding: 10px 16px;
  background: var(--surface-hover, #faf3ea);
  border-radius: 8px;
  margin: 8px 24px;
}

.msg-block {
  padding: 4px 0;
  font-size: 13px;
  line-height: 1.5;
  border-bottom: 1px dashed rgba(0,0,0,0.05);
}

.msg-block:last-child {
  border-bottom: none;
}

.msg-role {
  font-weight: 600;
  color: #b06a2e;
  margin-right: 8px;
}

.msg-content {
  color: #4a3520;
  word-break: break-word;
}

.col-empty-inner {
  font-size: 12px;
  color: #a9815a;
  padding: 8px 0;
  text-align: center;
}

/* 批量清理条：仅在存在「已移除」对话时出现 */
.batch-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 8px;
  padding: 8px 12px;
  border-radius: 8px;
  background: rgba(245, 247, 250, 0.9);
  border: 1px solid var(--border-color, #e9e0d4);
}

.batch-hint {
  font-size: 12px;
  color: #909399;
}

.batch-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

/* 移动端：批量操作条纵向排布，按钮不挤压 */
@media (max-width: 768px) {
  .batch-bar {
    flex-direction: column;
    align-items: stretch;
  }

  .batch-actions {
    justify-content: flex-end;
  }
}

.admin-tabs {
  margin-top: 8px;
}

.persona-link {
  color: var(--brand, #b06a2e);
  cursor: pointer;
  text-decoration: underline;
  text-underline-offset: 2px;
}

.persona-link:hover {
  opacity: 0.8;
}

/* 混合筛选区 */
.filter-panel {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  padding: 10px 12px;
  margin-bottom: 12px;
  background: var(--surface, #fff);
  border: 1px solid var(--border-color, #e9e0d4);
  border-radius: 10px;
}

.filter-input {
  width: 200px;
}

.filter-select {
  width: 150px;
}

.filter-count {
  font-size: 12px;
  color: #a9815a;
  margin-left: auto;
}

/* 头像预览 */
.avatar-cell {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.avatar-thumb {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  object-fit: cover;
  border: 1px solid var(--border-color, #e9e0d4);
  cursor: zoom-in;
  flex: none;
}

.avatar-thumb.avatar-ai {
  border-radius: 8px;
}

.avatar-fallback {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 600;
  color: #a9815a;
  background: var(--surface-hover, #faf3ea);
  cursor: default;
}

.msg-count-link {
  color: var(--brand, #b06a2e);
  cursor: pointer;
  text-decoration: underline;
  text-underline-offset: 2px;
  font-weight: 600;
}

/* 操作列图标按钮：更紧凑，一行排列 */
.inner-table :deep(.el-button + .el-button) {
  margin-left: 4px;
}

.inner-table :deep(.el-button--small) {
  padding: 5px 8px;
}

/* 卡片广场操作列：让「查看 / 删除」两个图标按钮水平排列，不会换行 */
.mp-actions {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  justify-content: center;
}
.mp-actions :deep(.el-button + .el-button) {
  margin-left: 0;
}
.mp-actions :deep(.el-button--small) {
  padding: 5px 8px;
}

/* 管理员卡片详情弹窗 */
.mp-detail-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.mp-detail-head {
  display: flex;
  align-items: center;
  gap: 16px;
}
.mp-detail-avatar {
  width: 80px;
  height: 80px;
  border-radius: 12px;
  object-fit: cover;
}
.mp-detail-meta {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.mp-detail-name {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
}
.mp-detail-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.mp-detail-stats {
  display: flex;
  gap: 14px;
  font-size: 13px;
  color: var(--text-secondary);
}
.mp-detail-stats .mp-stat {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.mp-detail-desc {
  margin: 0;
  font-size: 13px;
  line-height: 1.6;
  color: var(--text-secondary);
}
.mp-detail-section {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.mp-detail-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}
.mp-detail-box {
  background: var(--surface-hover);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 10px 12px;
  font-size: 13px;
  line-height: 1.6;
  color: var(--text-secondary);
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 280px;
  overflow-y: auto;
}
.mp-detail-greeting {
  border-left: 3px solid var(--brand);
}

.mp-comments-section {
  border-top: 1px solid var(--border-color);
  padding-top: 12px;
}

.mp-comments-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.mp-no-comments {
  font-size: 13px;
  color: var(--text-muted);
  padding: 12px 0;
}

.mp-comment {
  background: var(--surface);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 10px 12px;
}

.mp-comment-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 6px;
}

.mp-comment-user {
  font-size: 13px;
  font-weight: 600;
  color: var(--brand);
}

.mp-comment-time {
  font-size: 11px;
  color: var(--text-muted);
}

.mp-comment-text {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.5;
  margin: 0;
  word-break: break-word;
}

.msg-count-link:hover {
  opacity: 0.75;
}

.bg-thumb {
  width: 40px;
  height: 28px;
  border-radius: 4px;
  object-fit: cover;
  border: 1px solid var(--border-color, #e9e0d4);
  cursor: zoom-in;
}

.pdm-avatar {
  width: 64px;
  height: 64px;
  border-radius: 10px;
  object-fit: cover;
  border: 1px solid var(--border-color, #e9e0d4);
  cursor: zoom-in;
  flex: none;
}

/* 对话消息抽屉 */
.msg-drawer {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.md-head {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--border-color, #e9e0d4);
}

.md-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary, #4a3520);
  word-break: break-word;
}

.md-meta {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.md-empty {
  font-size: 13px;
  color: #a9815a;
  text-align: center;
  padding: 24px 0;
}

.md-msg {
  padding: 10px 12px;
  border-radius: 10px;
  background: var(--surface-hover, #faf3ea);
  border: 1px solid var(--border-color, #e9e0d4);
}

.md-msg.user {
  background: rgba(176, 106, 46, 0.08);
}

.md-msg-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}

.md-role {
  font-size: 12px;
  font-weight: 600;
  color: #b06a2e;
}

.md-time {
  font-size: 12px;
  color: #a9815a;
}

.md-content {
  font-size: 13px;
  line-height: 1.6;
  color: var(--text-primary, #4a3520);
  white-space: pre-wrap;
  word-break: break-word;
}

.md-image {
  margin-top: 8px;
  max-width: 220px;
  max-height: 220px;
  border-radius: 8px;
  cursor: zoom-in;
}

.persona-detail-modal {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.pdm-row {
  display: flex;
  align-items: center;
  gap: 14px;
}

.pdm-info h3 {
  margin: 0 0 4px;
  font-size: 16px;
  color: var(--text-primary, #4a3520);
}

.pdm-info p {
  margin: 0;
  font-size: 13px;
  color: var(--text-secondary, #8a6a48);
  line-height: 1.5;
}

.pdm-section {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.pdm-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary, #4a3520);
}

.pdm-box {
  background: var(--surface-hover, #faf3ea);
  border: 1px solid var(--border-color, #e9e0d4);
  border-radius: 8px;
  padding: 10px 12px;
  font-size: 13px;
  color: var(--text-secondary, #8a6a48);
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 200px;
  overflow-y: auto;
}

/* 反馈列表：用户头像+信息 */
.feedback-user {
  display: flex;
  align-items: center;
  gap: 8px;
}

.feedback-user-meta {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.feedback-username {
  font-size: 13px;
  color: var(--text-primary);
  font-weight: 500;
}

.feedback-email {
  font-size: 11px;
  color: var(--text-muted);
}

/* 反馈内容：截断显示 + 点击看详情 */
.feedback-content-cell {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
}

.feedback-content-text {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
  color: var(--text-secondary);
}

.feedback-content-more {
  flex: none;
  font-size: 12px;
  color: var(--brand);
  opacity: 0.85;
}

.feedback-content-cell:hover .feedback-content-more {
  opacity: 1;
  text-decoration: underline;
}

/* 反馈详情弹窗 */
.fb-detail {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.fb-detail-user {
  display: flex;
  align-items: center;
  gap: 10px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--border-color);
}

.fb-detail-user-meta {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  flex: 1;
}

.fb-detail-username {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.fb-detail-email {
  font-size: 12px;
  color: var(--text-muted);
}

.fb-detail-row {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 13px;
  color: var(--text-secondary);
}

.fb-detail-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-primary);
  min-width: 76px;
}

.fb-detail-contact {
  word-break: break-all;
}

.fb-detail-content {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.fb-detail-text {
  background: var(--surface-hover);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 10px 12px;
  font-size: 13px;
  line-height: 1.65;
  color: var(--text-secondary);
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 320px;
  overflow-y: auto;
}

/* 移动端 */
@media (max-width: 768px) {
  .admin-main {
    padding: 14px;
  }
  .admin-stats {
    grid-template-columns: repeat(2, 1fr);
  }
  .admin-header {
    padding: 12px 14px;
  }
  .filter-input,
  .filter-select {
    width: calc(50% - 4px);
  }
  .filter-count {
    margin-left: 0;
  }
  .admin-table :deep(.el-table__cell),
  .admin-table :deep(th.el-table__cell) {
    padding: 6px 4px;
  }
}

/* 提示词记录详情 */
.pl-detail-block { margin-bottom: 14px; }
.pl-detail-label {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 6px;
  font-size: 12.5px;
  font-weight: 600;
  color: var(--text-primary, #2a2522);
}
.pl-detail-text {
  margin: 0;
  max-height: 220px;
  overflow-y: auto;
  padding: 10px 12px;
  font-family: var(--font-mono, monospace);
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
  color: var(--text-secondary, #6a5d53);
  background: var(--surface-hover, #ebe4de);
  border: 1px solid var(--border-color, #e7ded6);
  border-radius: 8px;
}

/* ===== 提示词记录 Tab 美化 ===== */
.pl-toolbar { animation: pl-fade-up 0.42s ease both; }
.pl-filter { animation: pl-fade-up 0.42s ease 0.06s both; }
.pl-table-card {
  animation: pl-fade-up 0.42s ease 0.12s both;
  padding: 6px 12px;
  background: var(--surface, #fff);
  border: 1px solid var(--border-color, #e9e0d4);
  border-radius: 12px;
}

@keyframes pl-fade-up {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}

@media (prefers-reduced-motion: reduce) {
  .pl-toolbar, .pl-filter, .pl-table-card { animation: none; }
}

.pl-title {
  display: flex;
  align-items: center;
  gap: 8px;
}
.pl-title-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 8px;
  background: rgba(176, 106, 46, 0.12);
  color: var(--brand, #b06a2e);
  font-size: 16px;
}
.pl-title-count {
  margin-left: 2px;
  padding: 1px 9px;
  font-size: 12px;
  font-weight: 600;
  color: var(--brand, #b06a2e);
  background: rgba(176, 106, 46, 0.12);
  border-radius: 999px;
}

.pl-filter .filter-input { width: 220px; }
.pl-filter .filter-select { width: 160px; }

.pl-table :deep(.el-table__row) {
  transition: background 0.15s ease;
}
.pl-table :deep(.el-table__row:hover > td) {
  background: var(--surface-hover, #faf3ea) !important;
}

/* 类型药丸 */
.pl-type-pill {
  display: inline-flex;
  align-items: center;
  padding: 2px 11px;
  font-size: 12px;
  font-weight: 600;
  line-height: 1.6;
  border-radius: 999px;
  white-space: nowrap;
}
.pl-type-pill.is-character {
  color: #b06a2e;
  background: rgba(176, 106, 46, 0.12);
}
.pl-type-pill.is-image {
  color: #2c8c7c;
  background: rgba(44, 140, 124, 0.12);
}

.pl-model-tag {
  font-family: var(--font-mono, monospace);
  font-size: 12px;
  color: var(--text-secondary, #6a5d53);
}
.pl-muted { color: var(--text-muted, #b9a98f); }

/* 内容列：单行省略，把表格剩余宽度用满 */
.pl-content-cell {
  display: block;
  font-size: 12px;
  line-height: 1.5;
  color: var(--text-secondary, #6a5d53);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 操作列按钮组 */
.pl-actions {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  justify-content: center;
}
.pl-actions :deep(.el-button + .el-button) { margin-left: 0; }
.pl-actions :deep(.el-button--small) { padding: 5px 8px; }

/* 对话素材缩略图 */
.media-thumb {
  width: 44px;
  height: 44px;
  border-radius: 6px;
  cursor: zoom-in;
}
.media-value-preview {
  font-family: var(--font-mono, monospace);
  font-size: 12px;
  color: var(--text-muted, #b9a98f);
}
/* 系统级素材：不归属任何对话，用弱化标签区分于具体对话标题 */
.media-scope-global {
  display: inline-block;
  padding: 1px 7px;
  border-radius: 9px;
  font-size: 12px;
  color: var(--text-muted, #b9a98f);
  background: rgba(255, 255, 255, .07);
}

.pl-pagination {
  margin-top: 14px;
  justify-content: flex-end;
}

/* 详情对话框：元信息条 */
.pl-meta-bar {
  display: grid;
  /* 4 项元信息（用户/类型/模型/时间）铺满一行，弹窗加宽后不再左右空旷 */
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px 16px;
  margin-bottom: 18px;
  padding: 12px 14px;
  background: var(--surface-hover, #faf3ea);
  border: 1px solid var(--border-color, #e9e0d4);
  border-radius: 10px;
}
.pl-meta-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
.pl-meta-key {
  font-size: 11.5px;
  color: var(--text-secondary, #6a5d53);
  letter-spacing: 0.02em;
}
.pl-meta-val {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary, #2a2522);
  word-break: break-word;
}
.pl-meta-sub {
  font-style: normal;
  font-weight: 400;
  font-size: 11.5px;
  color: var(--text-muted, #a9815a);
  margin-left: 6px;
}

/* 详情块标签前的彩色圆点 */
.pl-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--text-muted, #a9815a);
  flex: none;
}
.pl-dot.is-brand { background: var(--brand, #b06a2e); }
.pl-dot.is-warn { background: #d9912b; }

/* 用户详情与 Token 用量 */
.user-detail { min-height: 320px; }
.detail-inline-tag { margin-left: 8px; }
.detail-muted { margin-left: auto; color: var(--text-muted, #a9815a); font-size: 12px; }
.detail-subtitle { margin: 18px 0 8px; font-weight: 700; color: var(--text-primary, #2a2522); }
.usage-cards { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; }
.usage-card { padding: 14px; border: 1px solid var(--border-color, #e9e0d4); border-radius: 10px; background: var(--surface-hover, #faf3ea); display: flex; flex-direction: column; gap: 4px; }
.usage-card b { font-size: 20px; color: var(--brand, #b06a2e); }
.usage-card span { font-size: 12px; color: var(--text-secondary, #6a5d53); }
.md-load-more { display: flex; justify-content: center; padding: 8px 0 14px; }
.md-msg-meta { display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 6px; color: var(--text-muted, #a9815a); font-size: 11.5px; }
.md-reasoning { margin-top: 8px; padding: 8px 10px; border-left: 3px solid var(--brand, #b06a2e); background: rgba(176, 106, 46, 0.06); color: var(--text-secondary, #6a5d53); white-space: pre-wrap; font-size: 12.5px; }

.support-toolbar { margin-top: 6px; }
.support-table { margin-bottom: 18px; }
.support-admin-chat { display: flex; flex-direction: column; gap: 14px; }
.support-admin-user { display: flex; align-items: center; gap: 10px; padding: 12px 14px; background: linear-gradient(135deg, rgba(176,106,46,.1), rgba(176,106,46,.02)); border: 1px solid rgba(176,106,46,.14); border-radius: 14px; }
.support-admin-user span { color: var(--text-muted); }
.support-admin-messages { height: min(50vh, 420px); min-height: 280px; overflow-y: auto; overscroll-behavior: contain; scrollbar-gutter: stable; display: flex; flex-direction: column; gap: 14px; padding: 8px 7px 8px 4px; }
.support-admin-msg { max-width: min(78%, 460px); padding: 10px 12px; border-radius: 14px 14px 14px 4px; background: var(--surface-hover); white-space: pre-wrap; box-shadow: 0 4px 14px rgba(0,0,0,.04); }
.support-admin-msg.admin { align-self: flex-end; border-radius: 14px 14px 4px 14px; background: rgba(176, 106, 46, .14); }
.support-admin-msg time { display: block; margin-top: 4px; font-size: 10.5px; color: var(--text-muted); }
.support-admin-image { display: block; max-width: 220px; max-height: 220px; margin-top: 6px; border-radius: 8px; }
.support-admin-image-preview :deep(.el-image) { max-height: 120px; }
.support-admin-reply { display: grid; grid-template-columns: auto minmax(0, 1fr) auto; align-items: center; gap: 9px; padding: 10px; border-radius: 18px; background: var(--surface); border: 1px solid var(--border-color); box-shadow: 0 8px 28px -18px rgba(44, 31, 22, .48); transition: border-color .18s ease, box-shadow .18s ease; }
.support-admin-reply:focus-within { border-color: var(--brand); box-shadow: 0 8px 28px -16px rgba(217, 108, 78, .5); }
.support-admin-reply :deep(.el-upload) { display: flex; }
.support-admin-reply :deep(.el-upload .el-button) { width: 40px; height: 40px; border-radius: 12px; }
.support-admin-reply :deep(.el-textarea__inner) { min-height: 64px !important; padding: 10px 12px; border-radius: 12px; background: var(--input-bg); box-shadow: 0 0 0 1px var(--border-color) inset; font-size: 13.5px; line-height: 1.55; color: var(--text-primary); resize: none; }
.support-admin-reply :deep(.el-textarea__inner:focus) { box-shadow: 0 0 0 1px var(--brand) inset; }
.support-admin-reply .el-button { min-height: 40px; border-radius: 12px; }

@media (max-width: 900px) {
  .pl-meta-bar { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .usage-cards { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}

@media (max-width: 560px) {
  .pl-meta-bar { grid-template-columns: 1fr; }
  .usage-cards { grid-template-columns: 1fr; }
  .support-admin-reply { grid-template-columns: auto minmax(0, 1fr); }
  .support-admin-reply .el-button { grid-column: 2; width: 100%; }
}
</style>
