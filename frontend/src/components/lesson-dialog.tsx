import { useId, useState } from "react"
import { toast } from "sonner"
import { errorMessage, lessonsApi } from "@/lib/api"
import type {
  Classroom,
  Group,
  LessonType,
  Subject,
  Teacher,
  TimeSlot,
  WeekParity,
} from "@/lib/models"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Label } from "@/components/ui/label"
import { ErrorNotice } from "@/components/feedback"

const dayNames = [
  "Понедельник",
  "Вторник",
  "Среда",
  "Четверг",
  "Пятница",
  "Суббота",
  "Воскресенье",
]

export function formatTimeSlot(slot: TimeSlot): string {
  const day = dayNames[slot.day_of_week - 1] || `День ${slot.day_of_week}`
  return `${day} · ${slot.slot_number} пара (${slot.start_time.slice(0, 5)}–${slot.end_time.slice(0, 5)})`
}

const selectClassName =
  "flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-xs transition-colors focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-50"

export function LessonDialog({
  groups,
  teachers,
  classrooms,
  subjects,
  timeSlots,
  onClose,
  onSaved,
}: {
  groups: Group[]
  teachers: Teacher[]
  classrooms: Classroom[]
  subjects: Subject[]
  timeSlots: TimeSlot[]
  onClose: () => void
  onSaved: () => void
}) {
  const baseId = useId()
  const [subjectId, setSubjectId] = useState(String(subjects[0]?.id || ""))
  const [groupId, setGroupId] = useState(String(groups[0]?.id || ""))
  const [teacherId, setTeacherId] = useState(String(teachers[0]?.id || ""))
  const [classroomId, setClassroomId] = useState(String(classrooms[0]?.id || ""))
  const [timeSlotId, setTimeSlotId] = useState(String(timeSlots[0]?.id || ""))
  const [lessonType, setLessonType] = useState<LessonType>("LECTURE")
  const [parity, setParity] = useState<WeekParity>("ALWAYS")
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!subjectId || !groupId || !teacherId || !classroomId || !timeSlotId) {
      setError("Выбери дисциплину, группу, преподавателя, аудиторию и временной слот.")
      return
    }
    setBusy(true)
    setError("")
    try {
      await lessonsApi.save({
        subject_id: Number(subjectId),
        group_id: Number(groupId),
        teacher_id: Number(teacherId),
        classroom_id: Number(classroomId),
        time_slot_id: Number(timeSlotId),
        lesson_type: lessonType,
        parity,
        specific_date: null,
      })
      toast.success("Занятие добавлено в расписание")
      onSaved()
      onClose()
    } catch (failure) {
      const msg = errorMessage(failure)
      setError(msg)
      toast.error(msg)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open && !busy) {
          onClose()
        }
      }}
    >
      <DialogContent
        className="max-h-[90dvh] overflow-y-auto sm:max-w-lg"
        onInteractOutside={(event) => {
          if (busy) {
            event.preventDefault()
          }
        }}
      >
        <DialogHeader>
          <DialogTitle>Добавить занятие</DialogTitle>
          <DialogDescription>
            Выбери параметры пары. Система автоматически проверит отсутствие накладок в расписании.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4" noValidate>
          <fieldset disabled={busy} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor={`${baseId}-subject`}>Дисциплина *</Label>
              <select
                id={`${baseId}-subject`}
                value={subjectId}
                onChange={(event) => setSubjectId(event.target.value)}
                className={selectClassName}
              >
                {subjects.map((subject) => (
                  <option key={subject.id} value={String(subject.id)}>
                    {subject.name}
                  </option>
                ))}
              </select>
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor={`${baseId}-group`}>Учебная группа *</Label>
                <select
                  id={`${baseId}-group`}
                  value={groupId}
                  onChange={(event) => setGroupId(event.target.value)}
                  className={selectClassName}
                >
                  {groups.map((group) => (
                    <option key={group.id} value={String(group.id)}>
                      {group.name}
                    </option>
                  ))}
                </select>
              </div>

              <div className="space-y-2">
                <Label htmlFor={`${baseId}-teacher`}>Преподаватель *</Label>
                <select
                  id={`${baseId}-teacher`}
                  value={teacherId}
                  onChange={(event) => setTeacherId(event.target.value)}
                  className={selectClassName}
                >
                  {teachers.map((teacher) => (
                    <option key={teacher.id} value={String(teacher.id)}>
                      {teacher.full_name}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor={`${baseId}-classroom`}>Аудитория *</Label>
                <select
                  id={`${baseId}-classroom`}
                  value={classroomId}
                  onChange={(event) => setClassroomId(event.target.value)}
                  className={selectClassName}
                >
                  {classrooms.map((classroom) => (
                    <option key={classroom.id} value={String(classroom.id)}>
                      {classroom.building} · {classroom.room_number} ({classroom.capacity} мест)
                    </option>
                  ))}
                </select>
              </div>

              <div className="space-y-2">
                <Label htmlFor={`${baseId}-slot`}>Временной слот *</Label>
                <select
                  id={`${baseId}-slot`}
                  value={timeSlotId}
                  onChange={(event) => setTimeSlotId(event.target.value)}
                  className={selectClassName}
                >
                  {timeSlots.map((slot) => (
                    <option key={slot.id} value={String(slot.id)}>
                      {formatTimeSlot(slot)}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor={`${baseId}-type`}>Тип занятия *</Label>
                <select
                  id={`${baseId}-type`}
                  value={lessonType}
                  onChange={(event) => setLessonType(event.target.value as LessonType)}
                  className={selectClassName}
                >
                  <option value="LECTURE">Лекция</option>
                  <option value="SEMINAR">Семинар</option>
                  <option value="LAB">Практикум</option>
                </select>
              </div>

              <div className="space-y-2">
                <Label htmlFor={`${baseId}-parity`}>Чётность недели *</Label>
                <select
                  id={`${baseId}-parity`}
                  value={parity}
                  onChange={(event) => setParity(event.target.value as WeekParity)}
                  className={selectClassName}
                >
                  <option value="ALWAYS">Каждую неделю</option>
                  <option value="ODD_WEEK">Нечётная</option>
                  <option value="EVEN_WEEK">Чётная</option>
                </select>
              </div>
            </div>
          </fieldset>

          {error && <ErrorNotice message={error} />}

          <DialogFooter>
            <Button type="button" variant="outline" disabled={busy} onClick={onClose}>
              Отмена
            </Button>
            <Button type="submit" disabled={busy}>
              {busy ? "Сохраняем" : "Сохранить"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
