using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Input;
namespace motion_trace_win;
public sealed partial class MainWindow
{
    private double leftWeight=35,videoWeight=30,rightWeight=35;
    private FrameworkElement? resizingDivider;
    private double dragStart,firstWidth,secondWidth;
    private void OnDividerPressed(object sender,PointerRoutedEventArgs e) {
        var element=(FrameworkElement)sender;var point=e.GetCurrentPoint(Workspace);
        if(!point.Properties.IsLeftButtonPressed || !element.CapturePointer(e.Pointer))return;
        resizingDivider=element;dragStart=point.Position.X;
        firstWidth=element==LeftDivider?VelocityColumn.ActualWidth:VideoColumn.ActualWidth;
        secondWidth=element==LeftDivider?VideoColumn.ActualWidth:ResultsColumn.ActualWidth;e.Handled=true;
    }
    private void OnDividerMoved(object sender,PointerRoutedEventArgs e) {
        if(resizingDivider is null)return;
        double sum=firstWidth+secondWidth,min=Math.Min(160,sum*.25);
        double first=Math.Clamp(firstWidth+e.GetCurrentPoint(Workspace).Position.X-dragStart,min,sum-min);
        double total=Math.Max(1,Workspace.ActualWidth-(DisplayAspectRatio<1?32:16));
        if(resizingDivider==LeftDivider){leftWeight=first/total*100;videoWeight=(sum-first)/total*100;}
        else if(DisplayAspectRatio<1){videoWeight=first/total*100;rightWeight=(sum-first)/total*100;}
        else {double proportion=leftWeight/(leftWeight+videoWeight);leftWeight=first/total*100*proportion;videoWeight=first/total*100*(1-proportion);rightWeight=(sum-first)/total*100;}
        UpdateWorkspaceLayout();e.Handled=true;
    }
    private void OnDividerReleased(object sender,PointerRoutedEventArgs e) {resizingDivider=null;((FrameworkElement)sender).ReleasePointerCapture(e.Pointer);e.Handled=true;}
    private void OnDividerCaptureLost(object sender,PointerRoutedEventArgs e)=>resizingDivider=null;
}
