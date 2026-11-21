import { lazy, StrictMode, Suspense } from "react"
import { createRoot } from "react-dom/client"
import { BrowserRouter, Link, Navigate, Route, Routes } from "react-router-dom"
import { AuthProvider } from "@/lib/auth"
import { AppLayout } from "@/components/app-layout"
import { RequireAuth } from "@/components/auth-guard"
import { LoadingRows } from "@/components/feedback"
import { Button } from "@/components/ui/button"
import { Toaster } from "@/components/ui/sonner"
import "@/index.css"

const LoginPage = lazy(() =>
  import("@/pages/login-page").then((module) => ({ default: module.LoginPage })),
)
const DirectoryPage = lazy(() =>
  import("@/pages/directory-page").then((module) => ({ default: module.DirectoryPage })),
)
const SchedulePage = lazy(() =>
  import("@/pages/schedule-page").then((module) => ({ default: module.SchedulePage })),
)
const UsersPage = lazy(() =>
  import("@/pages/users-page").then((module) => ({ default: module.UsersPage })),
)

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <Suspense fallback={<LoadingRows />}>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route element={<RequireAuth />}>
              <Route element={<AppLayout />}>
                <Route index element={<Navigate to="/schedule" replace />} />
                <Route path="schedule" element={<SchedulePage />} />
                <Route path="groups" element={<DirectoryPage key="groups" resource="groups" />} />
                <Route
                  path="teachers"
                  element={<DirectoryPage key="teachers" resource="teachers" />}
                />
                <Route
                  path="classrooms"
                  element={<DirectoryPage key="classrooms" resource="classrooms" />}
                />
                <Route
                  path="subjects"
                  element={<DirectoryPage key="subjects" resource="subjects" />}
                />
                <Route path="users" element={<UsersPage />} />
                <Route
                  path="*"
                  element={
                    <div className="space-y-4">
                      <h1 className="text-2xl font-semibold">Страница не найдена</h1>
                      <Button asChild>
                        <Link to="/schedule">Открыть расписание</Link>
                      </Button>
                    </div>
                  }
                />
              </Route>
            </Route>
          </Routes>
        </Suspense>
      </AuthProvider>
    </BrowserRouter>
    <Toaster theme="light" position="bottom-right" richColors closeButton />
  </StrictMode>,
)
