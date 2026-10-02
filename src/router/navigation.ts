/** 网站的“菜单总清单”
1. 左侧有哪些一级菜单。
2. 一级菜单从上到下的顺序。
3. 每个模块有哪些二级页签。
4. 菜单的名称、网址、图标和介绍文字。
*/

export interface NavItem {
  path: string  
  title: string
  icon: string
  description: string
  tabs: { path: string; title: string }[]
}
const tabs = (paths: string[], titles: string[]) =>
  paths.map((path, index) => ({ path, title: titles[index] || path }))
export const navigation: NavItem[] = [
  {
    path: '/dashboard',  /* 一级网址 */
    title: '综合态势',  /* 中文名称 */
    icon: 'HomeFilled',  /* 使用名叫 Coin 的图标 */
    description: '数据驱动 · 智能治理 · 全链路合规 · 赋能行业应用',  /* 页面介绍 */
    tabs: [],  /* 二级页面 */
  },
  {
    path: '/data-resource',
    title: '数据资源',
    icon: 'Coin',
    description: '汇聚多源数据，构建高质量、安全可信的数据资源体系',
    tabs: tabs(['ingest', 'datasets', 'statistics'], ['数据接入', '数据集管理', '数据资源统计']),
  },
  {
    path: '/data-governance',
    title: '数据治理',
    icon: 'Share',
    description: '数据处理 · 编排治理流程，生成可用数据版本',
    tabs: tabs(
      ['process', 'value-analysis', 'anomaly', 'risk-classification'],
      ['数据处理', '数据价值分析', '异常数据治理', '风险识别与分级'],
    ),
  },
  {
    path: '/model-train',
    title: '模型训推',
    icon: 'Box',
    description: '一站式模型训练、管理、评估、部署、调用，打造安全可靠的大模型能力',
    tabs: tabs(
      ['training', 'management', 'evaluation', 'deploy', 'invoke'],
      ['模型训练', '模型管理', '模型评估', '模型部署', '模型调用'],
    ),
  },
  {
    path: '/compliance',
    title: '全链路合规治理',
    icon: 'Checked',
    description: '贯通数据谱系、训练监控、推理审计，构建全链路可追溯的内容安全体系',
    tabs: tabs(
      [  /** 二级标签的 path */
        'lineage',
        'training-monitor',
        'reasoning-audit',
        'neuron-audit',
        'risk-alert',
        'full-chain',
      ],
      [  /** 二级标签的title */
        '数据谱系追踪',
        '训练行为监控',
        '推理路径审计',
        '神经元激活审计',
        '合规风险预警',
        '全链路追踪',
      ],
    ),
  },
  {
    path: '/evaluation',
    title: '测试评估',
    icon: 'DataAnalysis',
    description: '围绕指标管理、测试执行、结果留痕，提供第三方检测支持',
    tabs: tabs(
      ['metrics', 'tasks', 'execution', 'results', 'records'],
      ['指标管理', '测试任务', '测试执行', '测试结果', '测试记录'],
    ),
  },
  {
    path: '/scenario',
    title: '场景应用',
    icon: 'Grid',
    description: '面向行业场景，让内容安全治理能力落地应用',
    tabs: tabs(
      [
        'public-opinion',
        'hot-events',
        'cross-cultural',
        'ethnic-governance',
        'smart-government',
        'cyber-security',
      ],
      ['舆情分析', '热点事件跟踪', '跨文化交流', '多民族社会治理', '智能政务', '网络空间安防'],
    ),
  },
  {
    path: '/system',
    title: '系统管理',
    icon: 'Setting',
    description: '统一用户、角色、模型配置与系统运行管理',
    tabs: tabs(
      ['users', 'roles', 'model-config', 'logs'],
      ['用户管理', '角色权限', '模型接入配置', '系统日志'],
    ),
  },
]
