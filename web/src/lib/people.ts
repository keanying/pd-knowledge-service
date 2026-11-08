/** 头像文字：人名（≤3 字）取后两字，其他取首字。 */
export function initials(name?: string | null) {
  const n = name || '?'
  return n.length <= 3 ? n.slice(-2) : n.slice(0, 1)
}

const WEEK = ['日', '一', '二', '三', '四', '五', '六']
export function todayText(d = new Date()) {
  return `${d.getFullYear()}年${d.getMonth() + 1}月${d.getDate()}日 星期${WEEK[d.getDay()]}`
}
export function weekday(iso: string) {
  return '周' + WEEK[new Date(iso + 'T00:00:00').getDay()]
}
export function greeting(d = new Date()) {
  const h = d.getHours()
  return h < 6 ? '夜深了' : h < 11 ? '早上好' : h < 13 ? '中午好' : h < 18 ? '下午好' : '晚上好'
}
