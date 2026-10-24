export interface Metadata {
  id: number
  created_at: string
  updated_at: string
}

export interface GroupInput {
  name: string
  faculty: string
  course_number: number
  student_count: number
  is_active: boolean
}

export interface TeacherInput {
  full_name: string
  email: string
  department: string
  position: string | null
  is_active: boolean
}

export interface ClassroomInput {
  building: string
  room_number: string
  capacity: number
  has_projector: boolean
  has_computers: boolean
  is_active: boolean
}

export interface SubjectInput {
  name: string
  code: string | null
  description: string
}

export type Group = GroupInput & Metadata
export type Teacher = TeacherInput & Metadata
export type Classroom = ClassroomInput & Metadata
export type Subject = SubjectInput & Metadata
export type DirectoryRecord = Group | Teacher | Classroom | Subject
export type Resource = "groups" | "teachers" | "classrooms" | "subjects"

export interface GroupFilters {
  course_number?: number
  faculty?: string
  is_active?: boolean
  skip?: number
  limit?: number
}

export interface TeacherFilters {
  department?: string
  is_active?: boolean
  skip?: number
  limit?: number
}

export interface ClassroomFilters {
  building?: string
  min_capacity?: number
  has_projector?: boolean
  has_computers?: boolean
  is_active?: boolean
  skip?: number
  limit?: number
}

export interface SubjectFilters {
  search?: string
  name?: string
  code?: string
  skip?: number
  limit?: number
}

export interface TimeSlot extends Metadata {
  slot_number: number
  start_time: string
  end_time: string
  day_of_week: number
}

export interface TimeSlotFilters {
  day_of_week?: number
  slot_number?: number
  skip?: number
  limit?: number
}

export type WeekParity = "ALWAYS" | "ODD_WEEK" | "EVEN_WEEK"
export type LessonType = "LECTURE" | "SEMINAR" | "LAB"

export interface LessonInput {
  subject_id: number
  teacher_id: number
  group_id: number
  classroom_id: number
  time_slot_id: number
  lesson_type: LessonType
  parity: WeekParity
  specific_date?: string | null
}

export interface Lesson extends Metadata {
  subject_id: number
  teacher_id: number
  group_id: number
  classroom_id: number
  time_slot_id: number
  lesson_type: LessonType
  parity: WeekParity
  specific_date: string | null
  subject: { id: number; name: string; code?: string | null; description?: string | null } | null
  teacher: (TeacherInput & { id: number }) | null
  group: (GroupInput & { id: number }) | null
  classroom: {
    id: number
    building: string
    room_number: string
    capacity: number
    has_projector: boolean
    has_computers: boolean
    is_active: boolean
  } | null
  time_slot: {
    id: number
    slot_number: number
    start_time: string
    end_time: string
    day_of_week: number
  } | null
}

export interface AvailableClassroomFilters {
  time_slot_id: number
  parity?: WeekParity
  min_capacity?: number
  requires_projector?: boolean
  requires_computers?: boolean
  building?: string
}

export interface Readiness {
  status: string
  app_name: string
  version: string
  database: string
}
