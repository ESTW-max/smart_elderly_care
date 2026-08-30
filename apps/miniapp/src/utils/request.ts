import { API_BASE_URL } from '@/config/env'

export class ApiError extends Error {
  statusCode?: number

  constructor(message: string, statusCode?: number) {
    super(message)
    this.name = 'ApiError'
    this.statusCode = statusCode
  }
}

interface RequestOptions extends Omit<UniApp.RequestOptions, 'url'> {
  url: string
}

export function request<T>(options: RequestOptions): Promise<T> {
  const url = options.url.startsWith('http') ? options.url : `${API_BASE_URL}${options.url}`

  return new Promise((resolve, reject) => {
    uni.request({
      ...options,
      url,
      success: (response) => {
        if (response.statusCode >= 200 && response.statusCode < 300) {
          resolve(response.data as T)
          return
        }

        reject(new ApiError(`请求失败（${response.statusCode}）`, response.statusCode))
      },
      fail: (error) => {
        reject(new ApiError(error.errMsg || '网络请求失败'))
      },
    })
  })
}
