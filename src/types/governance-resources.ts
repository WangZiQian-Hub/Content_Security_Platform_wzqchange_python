export interface GovernanceResource {
  id: number
  name: string
  // id 是版本号字符串（v1.0.1），不是 dataset_versions 的自增主键。
  versions: { id: string; label: string; languages: { code: string; name: string }[] }[]
}
