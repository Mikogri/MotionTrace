"""Burn already computed, selection-filtered poses into video; never run inference."""
import json, sys
from fractions import Fraction
from pathlib import Path
import av, cv2
from motiontrace_ai.video_decode import VideoDecoder

BONES=[(5,6),(5,7),(7,9),(6,8),(8,10),(5,11),(6,12),(11,12),(11,13),(13,15),(12,14),(14,16),(0,1),(0,2),(1,3),(2,4)]
PALETTE=[(105,243,185),(255,205,97),(106,183,255),(255,151,208)]
JOINTS=['Nose','LeftEye','RightEye','LeftEar','RightEar','LeftShoulder','RightShoulder',
        'LeftElbow','RightElbow','LeftWrist','RightWrist','LeftHip','RightHip','LeftKnee','RightKnee','LeftAnkle','RightAnkle']

def render_frame(frame):
    """Accept schema transport JSON and earlier domain exports without inference."""
    if 'Athletes' in frame:return frame
    def caps(value):
        if isinstance(value,dict):return {k[0].upper()+k[1:]:caps(v) for k,v in value.items()}
        if isinstance(value,list):return [caps(v) for v in value]
        return value
    result=caps(frame)
    for pose in result['Athletes']:
        if pose.get('TrackingState')=='Lost':pose['TrackingState']=1
        for point in pose['Keypoints']:
            if isinstance(point['Joint'],str):point['Joint']=JOINTS.index(point['Joint'])
            point['Position']=dict(X=point['X'],Y=point['Y'])
            point['RawPosition']=point['Position']
    return result
def draw(image, frame, debug=False):
    if not frame:return
    frame=render_frame(frame)
    shafts=frame.get('Shafts')
    if shafts is None:shafts=[frame['Shaft']] if frame.get('Shaft') else []
    selected={p['AthleteId'] for p in frame['Athletes']}
    for obj in frame.get('Objects') or []:
        if obj.get('AthleteId') not in selected or obj.get('TrackingState') in (1,'Lost'):continue
        box=obj.get('Box')
        if box is not None:
            a=(round(box['X']),round(box['Y']))
            b=(round(box['X']+box['Width']),round(box['Y']+box['Height']))
            cv2.rectangle(image,a,b,(255,200,80),1)
        point=obj.get('Measurement')
        if point:
            color=(32,165,218) if point.get('IsProxy') else (255,255,0)
            cv2.drawMarker(image,(round(point['X']),round(point['Y'])),color,cv2.MARKER_CROSS,12,2)
    for shaft in shafts:
        if shaft.get('AthleteId') not in selected:continue
        color=(255,255,0) if shaft['MotionReliable'] else (32,165,218)
        for s in shaft['Segments']:cv2.line(image,(round(s['X1']),round(s['Y1'])),(round(s['X2']),round(s['Y2'])),color,3,cv2.LINE_AA)
    for pose in frame['Athletes']:
        color=PALETTE[(pose['AthleteId']-1)%4];box=pose['BoundingBox']
        x,y,w,h=[round(box[k]) for k in ('X','Y','Width','Height')]
        cv2.rectangle(image,(x,y),(x+w,y+h),color,1)
        cv2.putText(image,f"Athlete {pose['AthleteId']}"+(" - Lost" if pose['TrackingState']==1 else ''),(max(0,x),max(20,y-8)),cv2.FONT_HERSHEY_SIMPLEX,.6,color,2,cv2.LINE_AA)
        if pose['TrackingState']==1:continue
        points={p['Joint']:p for p in pose['Keypoints'] if p['Confidence']>=.4}
        xy=lambda p:(round(p['Position']['X']),round(p['Position']['Y']))
        for a,b in BONES:
            if a in points and b in points:cv2.line(image,xy(points[a]),xy(points[b]),color,2,cv2.LINE_AA)
        for p in points.values():cv2.circle(image,xy(p),3,color,-1,cv2.LINE_AA)
        if debug:
            for p in pose['Keypoints']:cv2.circle(image,(round(p['RawPosition']['X']),round(p['RawPosition']['Y'])),3,(0,69,255),1)

def export(source, analysis, target, debug=False, overlay=True):
    data=json.loads(Path(analysis).read_text(encoding='utf-8-sig'))
    frames=data['Frames'] if 'Frames' in data else data['frames'];index=-1
    timestamp=lambda frame:frame['TimestampSeconds'] if 'TimestampSeconds' in frame else frame['timestampSeconds']
    silent=str(Path(target).with_suffix('.silent.mp4'))
    decoder=VideoDecoder(source)
    try:
        with av.open(silent,'w') as out:
            stream=out.add_stream('libx264',rate=Fraction(decoder.fps).limit_denominator(100000))
            stream.width=decoder.width;stream.height=decoder.height;stream.pix_fmt='yuv420p'
            stream.time_base=Fraction(1,90000);stream.codec_context.time_base=stream.time_base
            stream.options={'crf':'18','preset':'fast'}
            for time,image in decoder:
                while index+1<len(frames) and timestamp(frames[index+1])<=time+1e-6:index+=1
                if overlay and index>=0 and time-timestamp(frames[index])<=.15:draw(image,frames[index],debug)
                frame=av.VideoFrame.from_ndarray(image,format='bgr24');frame.pts=round(time*90000);frame.time_base=Fraction(1,90000)
                for packet in stream.encode(frame):out.mux(packet)
            for packet in stream.encode():out.mux(packet)
        # Copy original audio packets; preserve timestamps and avoid generation loss.
        with av.open(silent) as video, av.open(source) as audio, av.open(target,'w') as out:
            vout=out.add_stream_from_template(video.streams.video[0])
            audio_map={s.index:out.add_stream_from_template(s) for s in audio.streams.audio}
            def packets(container,streams,mapping):
                for packet in container.demux(streams):
                    if packet.dts is None:continue
                    packet.stream=mapping[packet.stream.index]
                    yield packet
            import heapq
            vp=packets(video,[video.streams.video[0]],{video.streams.video[0].index:vout})
            ap=packets(audio,list(audio.streams.audio),audio_map) if audio_map else iter(())
            for packet in heapq.merge(vp,ap,key=lambda p:float(p.dts*p.time_base)):out.mux(packet)
    finally:
        decoder.close();Path(silent).unlink(missing_ok=True)
if __name__=='__main__':export(sys.argv[1],sys.argv[2],sys.argv[3],'--debug' in sys.argv,'--no-overlay' not in sys.argv)
