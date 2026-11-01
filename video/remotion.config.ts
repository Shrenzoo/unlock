import { Config } from '@remotion/cli/config'

Config.setVideoImageFormat('jpeg')
Config.setOverwriteOutput(true)
// WebGL for the real CAD meshes.
Config.setChromiumOpenGlRenderer('angle')
