# RealWorld (Conduit) Backend API Spec

Node.js + Express + SQLite로 아래 REST API를 구현하라. 서버는 `PORT` 환경변수(기본 3000)에서 기동되고, 모든 엔드포인트는 `/api` 프리픽스 아래에 둔다. `npm start`로 기동돼야 한다.

## 인증
- JWT 기반. `Authorization: Token <jwt>` 헤더.
- 응답의 User 객체: `{ user: { email, token, username, bio, image } }`.

## 엔드포인트
- POST `/api/users` — 회원가입 `{ user: { username, email, password } }`
- POST `/api/users/login` — 로그인 `{ user: { email, password } }`
- GET `/api/user` — 현재 사용자(인증 필요)
- PUT `/api/user` — 사용자 수정(인증)
- GET `/api/profiles/:username` — 프로필
- POST/DELETE `/api/profiles/:username/follow` — 팔로우/언팔로우(인증)
- GET `/api/articles` — 목록(필터: tag, author, favorited, limit, offset)
- GET `/api/articles/feed` — 팔로우 피드(인증)
- GET `/api/articles/:slug` — 단건
- POST `/api/articles` — 생성 `{ article: { title, description, body, tagList } }`(인증)
- PUT `/api/articles/:slug` — 수정(인증)
- DELETE `/api/articles/:slug` — 삭제(인증)
- POST/DELETE `/api/articles/:slug/favorite` — 즐겨찾기(인증)
- GET `/api/articles/:slug/comments` — 댓글 목록
- POST `/api/articles/:slug/comments` — 댓글 작성(인증)
- DELETE `/api/articles/:slug/comments/:id` — 댓글 삭제(인증)
- GET `/api/tags` — 태그 목록

## 응답 형태
- Article: `{ article: { slug, title, description, body, tagList, createdAt, updatedAt, favorited, favoritesCount, author: {username,bio,image,following} } }`
- 목록은 `{ articles: [...], articlesCount: N }`.
- 검증 오류: 422 `{ errors: { body: ["can't be blank"] } }`.

전체 공식 명세: https://realworld-docs.netlify.app/specifications/backend/endpoints/
스펙을 만족하는 실행 가능한 서버를 목표로 하라.
