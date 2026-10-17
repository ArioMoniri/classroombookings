// Frame rate of the whole pipeline (raw CFR transcode, camera, compositor, GIF clips). REC_FPS, default 30.
// The README set uses 20: a GIF frame delay is a whole number of 1/100 s, and 20 fps (5/100 s) is the
// fastest rate in 20-24 fps that GIF can keep exactly; 24 fps would alternate 4 and 5 and stutter.
export const FPS = Number(process.env.REC_FPS ?? 30);
