import { Answers } from './scenes/Answers'
import { Checks } from './scenes/Checks'
import { EndCard } from './scenes/EndCard'
import { LiveRun } from './scenes/LiveRun'
import { Title } from './scenes/Title'
import { Tools } from './scenes/Tools'

// In the order the demo plan uses them.
export const SCENES = [
  { id: 'Title', component: Title, seconds: 5 },
  { id: 'Tools', component: Tools, seconds: 6 },
  { id: 'LiveRun', component: LiveRun, seconds: 30 },
  { id: 'Checks', component: Checks, seconds: 8 },
  { id: 'Answers', component: Answers, seconds: 9 },
  { id: 'EndCard', component: EndCard, seconds: 6 },
]
