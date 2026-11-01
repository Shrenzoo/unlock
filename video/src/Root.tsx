import { Composition, Folder } from 'remotion'
import { All } from './scenes/All'
import { SCENES } from './sceneList'
import { FPS } from './theme'

export const RemotionRoot: React.FC = () => (
  <>
    <Folder name="Scenes">
      {SCENES.map(({ id, component, seconds }) => (
        <Composition
          key={id}
          id={id}
          component={component}
          durationInFrames={Math.round(seconds * FPS)}
          fps={FPS}
          width={1920}
          height={1080}
        />
      ))}
    </Folder>
    <Composition
      id="AllScenes"
      component={All}
      durationInFrames={SCENES.reduce((n, s) => n + Math.round(s.seconds * FPS), 0)}
      fps={FPS}
      width={1920}
      height={1080}
    />
  </>
)
