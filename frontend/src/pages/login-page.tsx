import { useId, useState } from "react"
import { CalendarDays, LogIn } from "lucide-react"
import { Navigate, useLocation, useNavigate } from "react-router-dom"
import { errorMessage } from "@/lib/api"
import { useAuth } from "@/lib/auth"
import { ErrorNotice } from "@/components/feedback"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"

interface LoginLocationState {
  from?: string
}

export function LoginPage() {
  const formId = useId()
  const navigate = useNavigate()
  const location = useLocation()
  const { status, sessionExpired, authNotice, login, clearAuthNotice } = useAuth()

  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")
  const [error, setError] = useState("")
  const [busy, setBusy] = useState(false)

  const state = location.state as LoginLocationState | null
  const redirectTo =
    state?.from && state.from !== "/login" && state.from.startsWith("/") ? state.from : "/schedule"

  if (status === "authenticated") {
    return <Navigate to={redirectTo} replace />
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const cleanedUsername = username.trim()
    if (!cleanedUsername) {
      setError("Введи логин учётной записи.")
      return
    }
    if (!password) {
      setError("Введи пароль.")
      return
    }
    setBusy(true)
    setError("")
    clearAuthNotice()
    try {
      await login({ username: cleanedUsername, password })
      navigate(redirectTo, { replace: true })
    } catch (failure) {
      setError(errorMessage(failure))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex min-h-dvh items-center justify-center bg-background px-4 py-10">
      <div className="w-full max-w-md space-y-6">
        <div className="flex items-center justify-center gap-3">
          <div className="flex size-11 items-center justify-center rounded-xl bg-primary text-primary-foreground">
            <CalendarDays className="size-6" aria-hidden="true" />
          </div>
          <div>
            <p className="text-base font-semibold tracking-tight">ScheduleService</p>
            <p className="text-xs text-muted-foreground">Учебный отдел</p>
          </div>
        </div>

        <Card className="shadow-xs">
          <CardHeader className="space-y-1.5">
            <CardTitle className="text-2xl">Вход в систему</CardTitle>
            <CardDescription>
              Введи логин и пароль учётной записи, чтобы открыть расписание и справочники.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-5">
            {sessionExpired && authNotice && (
              <div
                role="alert"
                className="rounded-lg border border-amber-500/40 bg-amber-500/10 p-4 text-sm text-foreground"
              >
                <p className="font-semibold">Сессия завершена</p>
                <p className="mt-1 text-muted-foreground">{authNotice}</p>
              </div>
            )}

            <form onSubmit={handleSubmit} className="space-y-4" noValidate>
              <fieldset disabled={busy} className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor={`${formId}-username`}>Логин</Label>
                  <Input
                    id={`${formId}-username`}
                    name="username"
                    type="text"
                    autoComplete="username"
                    autoFocus
                    value={username}
                    onChange={(event) => setUsername(event.target.value)}
                    placeholder="Например, admin"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor={`${formId}-password`}>Пароль</Label>
                  <Input
                    id={`${formId}-password`}
                    name="password"
                    type="password"
                    autoComplete="current-password"
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    placeholder="Введи пароль"
                  />
                </div>
              </fieldset>

              {error && <ErrorNotice message={error} />}

              <Button type="submit" className="w-full" disabled={busy}>
                <LogIn aria-hidden="true" />
                {busy ? "Выполняем вход..." : "Войти"}
              </Button>
            </form>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
