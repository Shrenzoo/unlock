import { Series } from 'remotion'
import { SCENES } from '../sceneList'

/** Every graphics scene back to back, for timing review. Edit the real cut in your NLE. */
export const All: React.FC = () => (
  <Series>
    {SCENES.map(({ id, component: Scene, seconds }) => (
      <Series.Sequence key={id} durationInFrames={Math.round(seconds * 30)}>
        <Scene />
      </Series.Sequence>
    ))}
  </Series>
)
