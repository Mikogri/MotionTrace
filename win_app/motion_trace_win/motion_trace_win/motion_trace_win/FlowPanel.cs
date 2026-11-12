using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Windows.Foundation;
namespace motion_trace_win;
public sealed class FlowPanel : Panel
{
    protected override Size MeasureOverride(Size available) {
        double x=0,y=0,h=0,width=0;
        foreach(var child in Children) {
            child.Measure(new Size(available.Width,double.PositiveInfinity));var d=child.DesiredSize;
            if(x>0 && x+d.Width>available.Width){y+=h;x=0;h=0;}
            x+=d.Width;h=Math.Max(h,d.Height);width=Math.Max(width,x);
        }
        return new Size(width,y+h);
    }
    protected override Size ArrangeOverride(Size finalSize) {
        double x=0,y=0,h=0;
        foreach(var child in Children) {
            var d=child.DesiredSize;
            if(x>0 && x+d.Width>finalSize.Width){y+=h;x=0;h=0;}
            child.Arrange(new Rect(x,y,Math.Min(d.Width,finalSize.Width),d.Height));x+=d.Width;h=Math.Max(h,d.Height);
        }
        return finalSize;
    }
}
