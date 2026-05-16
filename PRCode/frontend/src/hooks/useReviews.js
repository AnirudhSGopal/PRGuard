import { useState, useEffect } from 'react'
import { getRepos, getIssues, getFiles } from '../api/client'

export const useRepos = () => {
  const [repos, setRepos] = useState([])
  const [loading, setLoading] = useState(true)

  const refresh = async () => {
    setLoading(true)
    try {
      const data = await getRepos()
      setRepos(data)
    } catch (err) {
      setRepos([])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    refresh()
  }, [])

  return { repos, loading, refresh }
}

export const useIssues = (repo) => {
  const [issues, setIssues] = useState([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!repo) return
    setLoading(true)
    getIssues(repo).then(data => {
      setIssues(data)
      setLoading(false)
    }).catch(err => {
      setIssues([])
      setLoading(false)
    })
  }, [repo])

  return { issues, setIssues, loading }
}

export const useFiles = (repo) => {
  const [files, setFiles] = useState([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!repo) return
    setLoading(true)
    getFiles(repo).then(data => {
      setFiles(data)
      setLoading(false)
    }).catch(err => {
      setFiles([])
      setLoading(false)
    })
  }, [repo])

  return { files, loading }
}