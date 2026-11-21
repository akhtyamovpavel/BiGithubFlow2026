import type { Lesson, WeekParity } from "@/lib/models"

export const DAY_NAMES = [
  "Понедельник",
  "Вторник",
  "Среда",
  "Четверг",
  "Пятница",
  "Суббота",
  "Воскресенье",
] as const

export interface WeekDayInfo {
  dayOfWeek: number
  dayName: string
  iso: string
  shortDate: string
}

export function parseIsoDate(iso: string): Date | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso)
  if (!m) return null
  const [y, mo, d] = [Number(m[1]), Number(m[2]), Number(m[3])]
  const date = new Date(Date.UTC(y, mo - 1, d))
  return date.getUTCFullYear() === y && date.getUTCMonth() === mo - 1 && date.getUTCDate() === d
    ? date
    : null
}

export function formatIsoDate(date: Date): string {
  const y = date.getUTCFullYear()
  const m = String(date.getUTCMonth() + 1).padStart(2, "0")
  const d = String(date.getUTCDate()).padStart(2, "0")
  return `${y}-${m}-${d}`
}

export function todayIsoDate(): string {
  const now = new Date()
  return formatIsoDate(new Date(Date.UTC(now.getFullYear(), now.getMonth(), now.getDate())))
}

export function formatRuDate(iso: string): string {
  const parsed = parseIsoDate(iso)
  if (!parsed) return iso
  const d = String(parsed.getUTCDate()).padStart(2, "0")
  const m = String(parsed.getUTCMonth() + 1).padStart(2, "0")
  return `${d}.${m}.${parsed.getUTCFullYear()}`
}

export function addDaysIso(iso: string, deltaDays: number): string {
  const parsed = parseIsoDate(iso)
  if (!parsed) return iso
  parsed.setUTCDate(parsed.getUTCDate() + deltaDays)
  return formatIsoDate(parsed)
}

export function getIsoWeekday(iso: string): number {
  const parsed = parseIsoDate(iso)
  if (!parsed) return 0
  return parsed.getUTCDay() || 7
}

export function getIsoWeekParity(iso: string): Exclude<WeekParity, "ALWAYS"> {
  const parsed = parseIsoDate(iso)
  if (!parsed) return "ODD_WEEK"
  const day = parsed.getUTCDay() || 7
  parsed.setUTCDate(parsed.getUTCDate() + 4 - day)
  const yearStart = new Date(Date.UTC(parsed.getUTCFullYear(), 0, 1))
  const week = Math.ceil(((parsed.getTime() - yearStart.getTime()) / 86400000 + 1) / 7)
  return week % 2 === 1 ? "ODD_WEEK" : "EVEN_WEEK"
}

export function getWeekDates(referenceIso: string): WeekDayInfo[] {
  const monday = addDaysIso(referenceIso, -(getIsoWeekday(referenceIso) - 1))
  return Array.from({ length: 6 }, (_, index) => {
    const iso = addDaysIso(monday, index)
    return {
      dayOfWeek: index + 1,
      dayName: DAY_NAMES[index],
      iso,
      shortDate: formatRuDate(iso).slice(0, 5),
    }
  })
}

export function isLessonScheduledOnDate(lesson: Lesson, isoDate: string): boolean {
  if (!lesson.time_slot || !parseIsoDate(isoDate)) return false
  if (lesson.time_slot.day_of_week !== getIsoWeekday(isoDate)) return false
  if (lesson.specific_date) return lesson.specific_date === isoDate
  return lesson.parity === "ALWAYS" || lesson.parity === getIsoWeekParity(isoDate)
}

export function suggestOccurrenceDate(lesson: Lesson, referenceIso?: string): string {
  if (lesson.specific_date) return lesson.specific_date
  const base = referenceIso && parseIsoDate(referenceIso) ? referenceIso : todayIsoDate()
  if (!lesson.time_slot) return base
  const inWeek = getWeekDates(base).find((d) => d.dayOfWeek === lesson.time_slot?.day_of_week)
  if (inWeek && isLessonScheduledOnDate(lesson, inWeek.iso)) return inWeek.iso
  for (let offset = 0; offset <= 21; offset += 1) {
    const candidate = addDaysIso(base, offset)
    if (isLessonScheduledOnDate(lesson, candidate)) return candidate
  }
  return inWeek?.iso || base
}
