using Microsoft.UI;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Shapes;
using Windows.Foundation;

namespace motion_trace_win.Features.VideoAnalysis;

internal static class MovementChartRenderer
{
    public static void Draw(Canvas canvas, IReadOnlyList<(double X,double Y,int Segment)> points,
        double xmax, double? commonMaximum=null, IReadOnlyList<(double Start,double End)>? highlights=null)
    {
        canvas.Children.Clear();
        double w=canvas.ActualWidth, h=canvas.ActualHeight;
        if(w<100 || h<50) return;
        var foreground=(Brush)Application.Current.Resources["TextFillColorSecondaryBrush"];
        var accent=(Brush)Application.Current.Resources["AccentFillColorDefaultBrush"];
        var axis=(Brush)Application.Current.Resources["DividerStrokeColorDefaultBrush"];
        const double left=42, bottom=24, top=8, right=12;
        double pw=w-left-right, ph=h-top-bottom;
        double min=Math.Min(0,points.Count>0?points.Min(p=>p.Y):0);
        double max=Math.Max(1,commonMaximum ?? (points.Count>0?points.Max(p=>p.Y):1));
        max=Math.Max(max,min+1); xmax=Math.Max(.1,xmax);
        double X(double x)=>left+x/xmax*pw;
        double Y(double y)=>top+(max-y)/(max-min)*ph;
        void Label(string text,double x,double y) {
            var label=new TextBlock {Text=text,FontSize=10,Foreground=foreground};
            Canvas.SetLeft(label,x);Canvas.SetTop(label,y);canvas.Children.Add(label);
        }
        if(highlights is not null)
            foreach(var region in highlights) {
                var rect=new Rectangle { Width=Math.Max(0,X(region.End)-X(region.Start)),Height=ph,Fill=accent,Opacity=.13};
                Canvas.SetLeft(rect,X(region.Start));Canvas.SetTop(rect,top);canvas.Children.Add(rect);
            }
        foreach(double y in new[]{min,(min+max)/2,max}) {
            canvas.Children.Add(new Line{X1=left,X2=w-right,Y1=Y(y),Y2=Y(y),Stroke=axis,StrokeThickness=1});
            Label($"{y:0}",0,Math.Max(0,Y(y)-7));
        }
        Label("0 s",left,h-bottom+5);Label($"{xmax/2:0.0}",X(xmax/2)-8,h-bottom+5);Label($"{xmax:0.0} s",w-45,h-bottom+5);
        foreach(var segment in points.GroupBy(p=>p.Segment)) {
            var line=new Polyline{Stroke=accent,StrokeThickness=2,StrokeLineJoin=PenLineJoin.Round};
            // Bound drawing cost while retaining local extrema in each horizontal pixel bucket.
            foreach(var bucket in segment.GroupBy(p=>(int)X(p.X))) {
                var candidates=new[]{bucket.First(),bucket.MinBy(p=>p.Y),bucket.MaxBy(p=>p.Y),bucket.Last()};
                foreach(var p in candidates.Distinct().OrderBy(p=>p.X)) line.Points.Add(new Point(X(p.X),Y(p.Y)));
            }
            if(line.Points.Count>1) canvas.Children.Add(line);
        }
        if(points.Count==0) Label("No phase data",left+5,top+ph/2-7);
    }
}
