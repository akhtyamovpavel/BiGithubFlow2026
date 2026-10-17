import type { Lesson, LessonType, WeekParity } from "@/lib/models"

const entries: [number, number, string, string, number, number, LessonType, WeekParity][] = [
  [1, 1, "Математический анализ", "Смирнова Анна Сергеевна", 1, 1, "LECTURE", "ALWAYS"],
  [1, 2, "Программирование", "Волков Дмитрий Ильич", 1, 2, "LAB", "ODD_WEEK"],
  [2, 2, "Линейная алгебра", "Смирнова Анна Сергеевна", 2, 1, "SEMINAR", "ALWAYS"],
  [2, 3, "Процесс DevOps", "Волков Дмитрий Ильич", 1, 2, "SEMINAR", "EVEN_WEEK"],
  [3, 1, "Математический анализ", "Смирнова Анна Сергеевна", 1, 1, "SEMINAR", "ALWAYS"],
  [3, 4, "Программирование", "Волков Дмитрий Ильич", 2, 2, "LAB", "ALWAYS"],
  [4, 2, "Линейная алгебра", "Смирнова Анна Сергеевна", 1, 1, "LECTURE", "EVEN_WEEK"],
  [5, 3, "Процесс DevOps", "Волков Дмитрий Ильич", 2, 2, "LECTURE", "ALWAYS"],
  [6, 1, "Программирование", "Волков Дмитрий Ильич", 1, 2, "SEMINAR", "ODD_WEEK"],
  [6, 6, "Линейная алгебра", "Смирнова Анна Сергеевна", 2, 1, "SEMINAR", "ALWAYS"],
]

export const DEMO_TIMES = [
  ["09:00", "10:30"],
  ["10:45", "12:15"],
  ["12:30", "14:00"],
  ["14:15", "15:45"],
  ["16:00", "17:30"],
  ["17:45", "19:15"],
]

export const demoLessons: Lesson[] = entries.map((entry, index) => {
  const [day, slot, subject, teacher, groupId, teacherId, type, parity] = entry
  return {
    id: index + 1,
    created_at: "2026-09-01T00:00:00Z",
    updated_at: "2026-09-01T00:00:00Z",
    subject_id: index + 1,
    teacher_id: teacherId,
    group_id: groupId,
    classroom_id: teacherId,
    time_slot_id: day * 10 + slot,
    lesson_type: type,
    parity,
    specific_date: null,
    subject: { id: index + 1, name: subject },
    teacher: {
      id: teacherId,
      full_name: teacher,
      email: `demo${teacherId}@example.ru`,
      department: "Демонстрационная кафедра",
      position: null,
      is_active: true,
    },
    group: {
      id: groupId,
      name: `Б05-20${groupId}`,
      faculty: "Бизнес-информатика",
      course_number: 2,
      student_count: 25,
      is_active: true,
    },
    classroom: {
      id: teacherId,
      building: "Главный корпус",
      room_number: `${teacherId}01`,
      capacity: 30,
      has_projector: true,
      has_computers: true,
      is_active: true,
    },
    time_slot: {
      id: day * 10 + slot,
      slot_number: slot,
      day_of_week: day,
      start_time: DEMO_TIMES[slot - 1][0],
      end_time: DEMO_TIMES[slot - 1][1],
    },
  }
})
