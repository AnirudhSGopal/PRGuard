import { Link } from 'react-router-dom'

export default function NotFound() {
  return (
    <main className="min-h-screen flex items-center justify-center">
      <div className="text-center">
        <p className="text-amber-400 text-6xl font-bold mb-4">404</p>
        <p className="text-white text-lg mb-2">Page not found</p>
        <p className="text-gray-500 text-sm mb-6">This route does not exist in PRGuard</p>
        <Link to="/" className="text-sm bg-amber-400 text-[#0d0f12] px-4 py-2 rounded font-medium hover:bg-amber-300 transition-all">
          Go home
        </Link>
      </div>
    </main>
  )
}