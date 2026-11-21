import { useEffect, useState } from "react"
import {
  BookOpen,
  Building2,
  CalendarDays,
  Check,
  GraduationCap,
  LogOut,
  Menu,
  ShieldCheck,
  Unplug,
  UserRound,
  Users,
} from "lucide-react"
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom"
import { toast } from "sonner"
import { getReadiness } from "@/lib/api"
import { ROLE_LABELS, useAuth } from "@/lib/auth"
import { cn } from "@/lib/utils"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet"

const workspaceNavigation = [
  { to: "/schedule", label: "Сетка расписания", icon: CalendarDays },
  { to: "/groups", label: "Академические группы", icon: Users },
  { to: "/teachers", label: "Преподаватели", icon: GraduationCap },
  { to: "/classrooms", label: "Аудитории", icon: Building2 },
  { to: "/subjects", label: "Предметы", icon: BookOpen },
]

const adminNavigation = [{ to: "/users", label: "Пользователи", icon: ShieldCheck }]

function Brand() {
  return (
    <div className="flex items-center gap-3">
      <div className="flex size-10 items-center justify-center rounded-xl bg-primary text-primary-foreground">
        <CalendarDays className="size-5" aria-hidden="true" />
      </div>
      <div>
        <p className="text-sm font-semibold tracking-tight">ScheduleService</p>
        <p className="mt-0.5 text-xs text-muted-foreground">Учебный отдел</p>
      </div>
    </div>
  )
}

function Navigation({ isAdmin, close }: { isAdmin: boolean; close?: () => void }) {
  return (
    <nav aria-label="Основная навигация" className="space-y-5">
      <div>
        <p className="mb-2 px-3 text-xs font-medium text-muted-foreground">Рабочее пространство</p>
        <div className="space-y-1">
          {workspaceNavigation.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              onClick={close}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-3 rounded-lg px-3 py-3 text-sm font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground",
                  isActive && "bg-primary/8 text-primary hover:bg-primary/10 hover:text-primary",
                )
              }
            >
              <item.icon className="size-4 shrink-0" aria-hidden="true" />
              {item.label}
            </NavLink>
          ))}
        </div>
      </div>

      {isAdmin && (
        <div>
          <p className="mb-2 px-3 text-xs font-medium text-muted-foreground">Администрирование</p>
          <div className="space-y-1">
            {adminNavigation.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                onClick={close}
                className={({ isActive }) =>
                  cn(
                    "flex items-center gap-3 rounded-lg px-3 py-3 text-sm font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground",
                    isActive && "bg-primary/8 text-primary hover:bg-primary/10 hover:text-primary",
                  )
                }
              >
                <item.icon className="size-4 shrink-0" aria-hidden="true" />
                {item.label}
              </NavLink>
            ))}
          </div>
        </div>
      )}
    </nav>
  )
}

function BackendStatus() {
  const [status, setStatus] = useState<"checking" | "ready" | "unavailable">("checking")
  useEffect(() => {
    const controller = new AbortController()
    async function check() {
      try {
        const readiness = await getReadiness(controller.signal)
        if (!controller.signal.aborted) {
          let state: "ready" | "unavailable" = "unavailable"
          if (readiness.status === "ok" && readiness.database === "ok") {
            state = "ready"
          }
          setStatus(state)
        }
      } catch {
        if (!controller.signal.aborted) {
          setStatus("unavailable")
        }
      }
    }
    void check()
    const interval = window.setInterval(() => void check(), 30000)
    return () => {
      controller.abort()
      window.clearInterval(interval)
    }
  }, [])

  return (
    <div role="status" aria-live="polite">
      <Badge
        variant="outline"
        className={cn(
          "gap-1.5 py-1.5 font-normal",
          status === "ready" && "border-primary/20 bg-primary/5 text-primary",
        )}
      >
        {status === "ready" && (
          <>
            <Check className="size-3.5" aria-hidden="true" />
            Сервис доступен
          </>
        )}
        {status === "unavailable" && (
          <>
            <Unplug className="size-3.5" aria-hidden="true" />
            Сервис недоступен
          </>
        )}
        {status === "checking" && "Проверяем связь"}
      </Badge>
    </div>
  )
}

export function AppLayout() {
  const [menuOpen, setMenuOpen] = useState(false)
  const [loggingOut, setLoggingOut] = useState(false)
  const location = useLocation()
  const navigate = useNavigate()
  const { user, isAdmin, logout } = useAuth()

  const allNavigation = [...workspaceNavigation, ...adminNavigation]
  const current = allNavigation.find((item) => location.pathname === item.to)

  async function handleLogout() {
    setLoggingOut(true)
    try {
      await logout()
      toast.success("Вы вышли из системы")
      navigate("/login", { replace: true })
    } finally {
      setLoggingOut(false)
    }
  }

  return (
    <div className="min-h-dvh bg-background text-foreground lg:grid lg:grid-cols-[256px_minmax(0,1fr)]">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-50 focus:rounded-md focus:bg-primary focus:p-3 focus:text-primary-foreground"
      >
        Перейти к содержимому
      </a>
      <aside className="sticky top-0 hidden h-dvh flex-col border-r bg-card px-4 py-7 lg:flex">
        <div className="mb-10 px-3">
          <Brand />
        </div>
        <Navigation isAdmin={isAdmin} />
        <div className="mt-auto border-t px-3 pt-5 text-xs leading-relaxed text-muted-foreground">
          Планируем учебную неделю и ведём справочники в одном месте.
        </div>
      </aside>
      <div className="min-w-0">
        <header className="flex min-h-20 flex-wrap items-center justify-between gap-3 border-b bg-card px-4 py-4 sm:px-8">
          <div className="flex items-center gap-3">
            <Sheet open={menuOpen} onOpenChange={setMenuOpen}>
              <SheetTrigger asChild>
                <Button
                  variant="outline"
                  size="icon"
                  className="lg:hidden"
                  aria-label="Открыть навигацию"
                >
                  <Menu aria-hidden="true" />
                </Button>
              </SheetTrigger>
              <SheetContent side="left" className="w-72 px-4">
                <SheetHeader className="px-2 pt-8">
                  <SheetTitle>
                    <Brand />
                  </SheetTitle>
                  <SheetDescription>Разделы учебного отдела</SheetDescription>
                </SheetHeader>
                <Navigation isAdmin={isAdmin} close={() => setMenuOpen(false)} />
              </SheetContent>
            </Sheet>
            <span className="hidden text-sm text-muted-foreground sm:inline">Учебный отдел</span>
            <span className="hidden text-muted-foreground/50 sm:inline" aria-hidden="true">
              /
            </span>
            <span className="text-sm font-medium">{current?.label || "Страница не найдена"}</span>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <BackendStatus />
            {user && (
              <div className="flex items-center gap-2 rounded-lg border bg-muted/30 px-3 py-1.5 text-sm">
                <UserRound className="size-4 text-muted-foreground" aria-hidden="true" />
                <span className="font-medium">{user.username}</span>
                <Badge variant="secondary" className="text-xs font-normal">
                  {ROLE_LABELS[user.role]}
                </Badge>
              </div>
            )}
            <Button
              variant="outline"
              size="sm"
              disabled={loggingOut}
              onClick={() => void handleLogout()}
            >
              <LogOut className="size-4" aria-hidden="true" />
              Выйти
            </Button>
          </div>
        </header>
        <main id="main" className="mx-auto max-w-[1720px] p-4 py-7 sm:p-8 lg:p-10" tabIndex={-1}>
          <Outlet />
        </main>
      </div>
    </div>
  )
}
