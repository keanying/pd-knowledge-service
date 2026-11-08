import type { Component } from 'vue'
import {
  IconHome, IconBookStroked, IconCheckList, IconComment, IconCustomerSupport, IconCloud, IconTestScoreStroked,
  IconHistogram, IconSetting,
} from '@kousum/semi-icons-vue'

export interface MenuLeaf {
  path: string
  title: string
  /** 满足其一即可见（与 PDS 中的 PDK 权限清单一致） */
  perms: string[]
  match?: string[]
  /** 骨架阶段尚未实现的页面 */
  todo?: boolean
}

export interface MenuGroup {
  key: string
  title: string
  icon: Component
  children: MenuLeaf[]
}

/** 菜单结构见《PDK 产品功能文档》§8。一级为图标，悬停浮出二级菜单（与 PDS 管理后台一致）。 */
export const menuGroups: MenuGroup[] = [
  { key: 'home', title: '工作台', icon: IconHome, children: [{ path: '/', title: '工作台', perms: ['pdk:console:access'] }] },
  { key: 'kb', title: '知识库', icon: IconBookStroked, children: [{ path: '/kbs', title: '知识库', perms: ['pdk:kb:view'] }] },
  { key: 'review', title: '审核中心', icon: IconCheckList, children: [{ path: '/reviews', title: '审核中心', perms: ['pdk:doc:review'] }] },
  {
    key: 'ops', title: '知识运营', icon: IconComment, children: [
      { path: '/tickets', title: '纠错工单', perms: ['pdk:update:review', 'pdk:kb:view'] },
      { path: '/gaps', title: '知识缺口', perms: ['pdk:stats:view'], todo: true },
      { path: '/expiry', title: '过期复核', perms: ['pdk:doc:edit'], todo: true },
      { path: '/hot', title: '热门问题', perms: ['pdk:stats:view'], todo: true },
    ],
  },
  {
    key: 'pda', title: '智能助手', icon: IconCustomerSupport, children: [
      { path: '/pda/persona', title: '人设与提示词', perms: ['pdk:pda:manage'], todo: true },
      { path: '/pda/tools', title: '工具与技能', perms: ['pdk:pda:manage'], todo: true },
      { path: '/pda/models', title: '模型路由', perms: ['pdk:pda:manage'], todo: true },
      { path: '/pda/welcome', title: '欢迎语与推荐问题', perms: ['pdk:pda:manage'], todo: true },
    ],
  },
  { key: 'source', title: '数据源', icon: IconCloud, children: [{ path: '/datasources', title: '数据源', perms: ['pdk:datasource:manage'], todo: true }] },
  { key: 'eval', title: '评测中心', icon: IconTestScoreStroked, children: [{ path: '/eval', title: '评测中心', perms: ['pdk:eval:manage'], todo: true }] },
  { key: 'stats', title: '统计分析', icon: IconHistogram, children: [{ path: '/stats', title: '统计分析', perms: ['pdk:stats:view'], todo: true }] },
  {
    key: 'sys', title: '系统设置', icon: IconSetting, children: [
      { path: '/tasks', title: '任务中心', perms: ['pdk:task:manage', 'pdk:doc:upload'] },
      { path: '/api-keys', title: '接口密钥', perms: ['pdk:apikey:manage'] },
      { path: '/models', title: '模型配置', perms: ['pdk:model:manage'], todo: true },
      { path: '/settings', title: '系统参数', perms: ['pdk:model:manage'], todo: true },
    ],
  },
]
