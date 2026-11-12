using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Shapes;
using MotionTrace.Core.Motion;
using Windows.Foundation;
using Windows.UI;
namespace motion_trace_win.Features.VideoAnalysis;

/// <summary>Reusable multi-source chart. Only the cursor and marker change during playback.</summary>
internal sealed class PlaybackChart
{
    private readonly Canvas canvas;
    public event Action? ScrubStarted;
    public event Action<double>? SeekRequested;
    public event Action? ScrubEnded;
    public string? ActiveRepId {get;set;}
    public string? ActiveSourceVideoId {get;set;}
    public string? ValueUnit {get;set;}
    private MotionChartSeries? dragSeries;
    private double playbackTime;
    public PlaybackChart(Canvas canvas)
    {
        this.canvas=canvas;
        canvas.Background=new SolidColorBrush(Microsoft.UI.Colors.Transparent);
        canvas.PointerPressed+=(_,e)=> {
            var point=e.GetCurrentPoint(canvas);
            if(!point.Properties.IsLeftButtonPressed || point.Position.X<48 || point.Position.X>canvas.ActualWidth-16 || point.Position.Y<12 || point.Position.Y>canvas.ActualHeight-32)return;
            var playable=series.Where(s=>ActiveSourceVideoId is null || s.SourceVideoId==ActiveSourceVideoId).ToArray();
            dragSeries=playable.FirstOrDefault(s=>s.RepId==ActiveRepId) ?? playable.FirstOrDefault(s=>playbackTime>=s.Start && playbackTime<=s.End) ?? playable.FirstOrDefault();
            if(dragSeries is null)return;
            if(!canvas.CapturePointer(e.Pointer)){dragSeries=null;return;}
            ScrubStarted?.Invoke();Seek(point.Position.X);e.Handled=true;
        };
        canvas.PointerMoved+=(_,e)=> {if(dragSeries is not null){Seek(e.GetCurrentPoint(canvas).Position.X);e.Handled=true;}};
        canvas.PointerReleased+=(_,e)=> {if(dragSeries is null)return;Seek(e.GetCurrentPoint(canvas).Position.X);EndDrag();canvas.ReleasePointerCapture(e.Pointer);e.Handled=true;};
        canvas.PointerCaptureLost+=(_,_)=>EndDrag();
        canvas.PointerCanceled+=(_,_)=>EndDrag();
    }
    private void EndDrag(){if(dragSeries is null)return;dragSeries=null;ScrubEnded?.Invoke();}
    private void Seek(double pixelX)
    {
        if(dragSeries?.TimestampAtX(xmin+Math.Clamp((pixelX-48)/Math.Max(1,canvas.ActualWidth-64),0,1)*(xmax-xmin),playbackTime) is {} time) {
            playbackTime=time;SeekRequested?.Invoke(time);Update(dragSeries.SourceVideoId,time);
        }
    }
    private readonly Line cursor=new(){StrokeThickness=1,IsHitTestVisible=false};
    private readonly Ellipse marker=new(){Width=8,Height=8,IsHitTestVisible=false};
    private IReadOnlyList<MotionChartSeries> series=[];
    private double xmin,xmax=1,min,max=1;
    private double X(double value)=>48+(value-xmin)/(xmax-xmin)*Math.Max(1,canvas.ActualWidth-64);
    private double Y(double value)=>12+(max-value)/(max-min)*Math.Max(1,canvas.ActualHeight-44);
    public static Brush ColorFor(string id)
    {
        if(string.IsNullOrEmpty(id))return new SolidColorBrush(Color.FromArgb(255,70,165,245));
        int.TryParse(id.Split('/')[^1],out int rep);
        double hue=(Math.Max(1,rep)-1)*2.399963229728653;
        byte C(double offset)=>(byte)Math.Round(155+85*Math.Cos(hue+offset));
        return new SolidColorBrush(Color.FromArgb(255,C(0),C(2.094395102),C(4.188790205)));
    }
    public static Brush PreparationColor => new SolidColorBrush(Color.FromArgb(255,180,130,235));
    public static Brush LoweringColor => new SolidColorBrush(Color.FromArgb(255,234,144,66));
    public static Brush PauseColor => new SolidColorBrush(Color.FromArgb(255,160,160,160));
    private static int Phase(MotionChartSeries s,double time) => s.PhaseAt(time) switch {0=>3,1=>0,2=>1,_=>2};
    public static Brush SeriesColor(MotionChartSeries s)=>ColorFor(s.PaletteIndex is {} index ? (index+1).ToString() : s.Id);
    private Brush PhaseColor(MotionChartSeries s,double time) => s.PaletteIndex is not null || series.Count>1?SeriesColor(s): Phase(s,time) switch {3=>PreparationColor,0=>LoweringColor,1=>PauseColor,_=>ColorFor("")};
    public void SetSeries(IReadOnlyList<MotionChartSeries> data)
    {
        EndDrag();series=data;canvas.Children.Clear();
        if(canvas.ActualWidth<100 || canvas.ActualHeight<60)return;
        var plotted=data.Select(s=>(Series:s,Points:s.Points.ToArray())).ToArray();
        var all=plotted.SelectMany(s=>s.Points).ToArray();
        bool rom=data.FirstOrDefault()?.Axis==MotionChartAxis.Rom;
        xmin=rom?0:Math.Min(0,data.Select(s=>s.Start-(s.TimeOrigin??s.Start)).DefaultIfEmpty(0).Min());
        xmax=rom?100:Math.Max(.1,data.Select(s=>s.End-(s.TimeOrigin??s.Start)).DefaultIfEmpty(1).Max());
        min=Math.Min(0,all.Select(p=>p.Y).DefaultIfEmpty(0).Min());
        max=Math.Max(1,all.Select(p=>p.Y).DefaultIfEmpty(1).Max());
        var foreground=(Brush)Application.Current.Resources["TextFillColorSecondaryBrush"];
        var grid=(Brush)Application.Current.Resources["DividerStrokeColorDefaultBrush"];
        void Label(string text,double x,double y) { var label=new TextBlock{Text=text,FontSize=10,Foreground=foreground};Canvas.SetLeft(label,x);Canvas.SetTop(label,y);canvas.Children.Add(label); }
        foreach(double y in new[]{min,(min+max)/2,max}) {
            canvas.Children.Add(new Line{X1=X(xmin),X2=X(xmax),Y1=Y(y),Y2=Y(y),Stroke=grid,StrokeThickness=1});
            Label($"{y:0.#}",0,Y(y)-7);
        }
        Label(rom?"0%":$"{xmin:0.##} s",X(xmin),canvas.ActualHeight-23);
        Label(rom?"50%":$"{(xmin+xmax)/2:0.##}",X((xmin+xmax)/2)-10,canvas.ActualHeight-23);
        Label(rom?"100%":$"{xmax:0.##} s",X(xmax)-32,canvas.ActualHeight-23);
        foreach(var item in plotted) {
            // Share the boundary point between colored runs, preserving a continuous trace.
            Polyline? line=null;
            int previousPhase=-1;
            for(int i=1;i<item.Points.Length;i++) {
                var a=item.Points[i-1];var b=item.Points[i];
                if(a.Segment!=b.Segment || b.Timestamp-a.Timestamp>.25) {line=null;continue;}
                int phase=Phase(item.Series,(a.Timestamp+b.Timestamp)/2);
                if(line is null || phase!=previousPhase) {
                    line=new Polyline {Stroke=PhaseColor(item.Series,(a.Timestamp+b.Timestamp)/2),StrokeThickness=2,StrokeLineJoin=PenLineJoin.Round};
                    line.Points.Add(new Point(X(a.X),Y(a.Y)));canvas.Children.Add(line);
                }
                line.Points.Add(new Point(X(b.X),Y(b.Y)));previousPhase=phase;
            }
            if(!rom)foreach(var boundary in new[]{item.Series.LoweringStart,item.Series.LoweringEnd,item.Series.LiftingStart,item.Series.LiftingEnd}.OfType<double>().Distinct()) {
                if(boundary<=item.Series.Start || boundary>=item.Series.End)continue;
                double x=X(boundary-(item.Series.TimeOrigin??item.Series.Start));
                canvas.Children.Add(new Line {X1=x,X2=x,Y1=12,Y2=canvas.ActualHeight-32,
                    Stroke=item.Series.PaletteIndex is not null?SeriesColor(item.Series):foreground,StrokeThickness=1,StrokeDashArray=new DoubleCollection{3,3},Opacity=.65});
            }
        }

        if(all.Length==0)Label(data.Count==0?"Select reps to show movement":"No reliable ROM data",X(0)+4,Y((min+max)/2));
        cursor.Stroke=(Brush)Application.Current.Resources["TextFillColorPrimaryBrush"];
        cursor.Y1=12;cursor.Y2=canvas.ActualHeight-32;
        cursor.Visibility=marker.Visibility=Visibility.Collapsed;
        canvas.Children.Add(cursor);canvas.Children.Add(marker);
    }
    public string Update(string videoId,double timestamp)
    {
        if(dragSeries is not null)timestamp=playbackTime;
        playbackTime=timestamp;
        foreach(var s in series.Where(s=>s.SourceVideoId==videoId).OrderByDescending(s=>s==dragSeries || s.RepId==ActiveRepId)) {
            if(s.At(timestamp) is not { } p)continue;
            cursor.Visibility=marker.Visibility=Visibility.Visible;
            cursor.X1=cursor.X2=X(p.X);marker.Fill=PhaseColor(s,timestamp);
            Canvas.SetLeft(marker,X(p.X)-4);Canvas.SetTop(marker,Y(p.Y)-4);
            return $"{s.DisplayName} · {timestamp:0.000} s · {p.Y:0.0} {ValueUnit ?? (s.Metric==MotionChartMetric.Velocity?"px/s":"px")}";
        }
        cursor.Visibility=marker.Visibility=Visibility.Collapsed;
        return $"{timestamp:0.000} s · outside selected movement";
    }
}
