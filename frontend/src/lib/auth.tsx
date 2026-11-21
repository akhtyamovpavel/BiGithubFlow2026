import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react"
import {
  ApiError,
  authApi,
  clearAccessToken,
  errorMessage,
  getAccessToken,
  setAccessToken,
  setUnauthorizedHandler,
} from "@/lib/api"
import type { LoginInput, User, UserRole } from "@/lib/models"

export const ROLE_LABELS: Record<UserRole, string> = {
  admin: "Администратор",
  dispatcher: "Диспетчер",
  reader: "Читатель",
}

export const SESSION_EXPIRED_MESSAGE =
  "Сессия истекла или была отозвана. Войди в систему повторно."

export type AuthStatus = "loading" | "authenticated" | "unauthenticated" | "error"

interface AuthContextValue {
  user: User | null
  status: AuthStatus
  sessionExpired: boolean
  authNotice: string
  bootError: string
  canEdit: boolean
  isAdmin: boolean
  login: (input: LoginInput) => Promise<User>
  logout: () => Promise<void>
  retryBootstrap: () => void
  clearAuthNotice: () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [status, setStatus] = useState<AuthStatus>(() =>
    getAccessToken() ? "loading" : "unauthenticated",
  )
  const [sessionExpired, setSessionExpired] = useState(false)
  const [authNotice, setAuthNotice] = useState("")
  const [bootError, setBootError] = useState("")
  const [bootRevision, setBootRevision] = useState(0)

  const handleSessionExpired = useCallback(() => {
    clearAccessToken()
    setUser(null)
    setStatus("unauthenticated")
    setSessionExpired(true)
    setAuthNotice(SESSION_EXPIRED_MESSAGE)
    setBootError("")
  }, [])

  useEffect(() => {
    setUnauthorizedHandler(handleSessionExpired)
    return () => setUnauthorizedHandler(null)
  }, [handleSessionExpired])

  useEffect(() => {
    const token = getAccessToken()
    if (!token) {
      setUser(null)
      setStatus("unauthenticated")
      setBootError("")
      return
    }
    const controller = new AbortController()
    setStatus("loading")
    setBootError("")
    authApi
      .me(controller.signal)
      .then((profile) => {
        if (!controller.signal.aborted) {
          setUser(profile)
          setStatus("authenticated")
          setSessionExpired(false)
          setAuthNotice("")
        }
      })
      .catch((failure) => {
        if (controller.signal.aborted) {
          return
        }
        if (failure instanceof ApiError && failure.status === 401) {
          handleSessionExpired()
        } else {
          setStatus("error")
          setBootError(errorMessage(failure))
        }
      })
    return () => controller.abort()
  }, [bootRevision, handleSessionExpired])

  const login = useCallback(async (input: LoginInput): Promise<User> => {
    const token = await authApi.login(input)
    setAccessToken(token.access_token)
    try {
      const profile = await authApi.me()
      setUser(profile)
      setStatus("authenticated")
      setSessionExpired(false)
      setAuthNotice("")
      setBootError("")
      return profile
    } catch (failure) {
      clearAccessToken()
      setUser(null)
      setStatus("unauthenticated")
      throw failure
    }
  }, [])

  const logout = useCallback(async (): Promise<void> => {
    try {
      if (getAccessToken()) {
        await authApi.logout()
      }
    } catch {
      // Even if the server session is already revoked, clear client state cleanly.
    } finally {
      clearAccessToken()
      setUser(null)
      setStatus("unauthenticated")
      setSessionExpired(false)
      setAuthNotice("")
      setBootError("")
    }
  }, [])

  const retryBootstrap = useCallback(() => {
    setBootRevision((value) => value + 1)
  }, [])

  const clearAuthNotice = useCallback(() => {
    setSessionExpired(false)
    setAuthNotice("")
  }, [])

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      status,
      sessionExpired,
      authNotice,
      bootError,
      canEdit: user?.role === "admin" || user?.role === "dispatcher",
      isAdmin: user?.role === "admin",
      login,
      logout,
      retryBootstrap,
      clearAuthNotice,
    }),
    [
      authNotice,
      bootError,
      clearAuthNotice,
      login,
      logout,
      retryBootstrap,
      sessionExpired,
      status,
      user,
    ],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error("useAuth must be used inside AuthProvider")
  }
  return context
}
