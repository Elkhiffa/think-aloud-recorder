/* Design prototype: generated examples only. No input hooks or captured user data. */
window.INPUT_REVIEW_FIXTURE = {
  duration: 32,
  video: 'demo.mp4',
  title: '通道入口 · 操作回看',
  segments: [
    { start: 4.2, end: 7.8, text: '我以为走近就能打开。这里是不是还需要按一个键？' },
    { start: 14.5, end: 18.2, text: '换成手柄试一下，看看这个提示会不会变。' },
    { start: 23.6, end: 27.3, text: '按住以后有变化了，但刚才没有注意到这个反馈。' }
  ],
  intervals: [
    { id:'k-w-1', start:1, end:8.2, device:'keyboard', code:'W', label:'W', kind:'button' },
    { id:'k-a-1', start:3.2, end:5.8, device:'keyboard', code:'A', label:'A', kind:'button' },
    { id:'k-q-1', start:4.5, end:4.95, device:'keyboard', code:'Q', label:'Q', kind:'button' },
    { id:'m-left-1', start:4.65, end:5.1, device:'mouse', code:'MouseLeft', label:'左键', kind:'button' },
    { id:'m-move-1', start:6.1, end:7.5, device:'mouse', code:'MouseMove', label:'鼠标', kind:'motion', direction:'↗', value:0.7, detail:'向右上移动' },
    { id:'k-e-1', start:8.5, end:8.65, device:'keyboard', code:'E', label:'E', kind:'button' },
    { id:'k-e-2', start:8.9, end:9.05, device:'keyboard', code:'E', label:'E', kind:'button' },
    { id:'k-e-3', start:9.3, end:9.45, device:'keyboard', code:'E', label:'E', kind:'button' },
    { id:'k-w-2', start:13.2, end:14.3, device:'keyboard', code:'W', label:'W', kind:'button' },
    { id:'x-left-1', start:15, end:20.4, device:'xbox', code:'LeftStick', label:'左摇杆', kind:'axis', direction:'↗', value:0.72, detail:'右上 72%' },
    { id:'x-lb-1', start:16, end:18.25, device:'xbox', code:'LB', label:'LB', kind:'button' },
    { id:'x-a-1', start:16.85, end:17.3, device:'xbox', code:'A', label:'A', kind:'button' },
    { id:'x-right-1', start:18, end:20, device:'xbox', code:'RightStick', label:'右摇杆', kind:'axis', direction:'→', value:0.42, detail:'向右 42%' },
    { id:'x-rt-1', start:18.7, end:20.3, device:'xbox', code:'RT', label:'RT', kind:'trigger', value:0.65, detail:'按压 65%' },
    { id:'p-left-1', start:23, end:28.2, device:'dualsense', code:'LeftStick', label:'左摇杆', kind:'axis', direction:'↑', value:0.86, detail:'向前 86%' },
    { id:'p-r2-1', start:24.3, end:27.1, device:'dualsense', code:'R2', label:'R2', kind:'trigger', value:0.78, detail:'按压 78%' },
    { id:'p-cross-1', start:25.1, end:25.55, device:'dualsense', code:'Cross', label:'×', kind:'button', detail:'交叉键' },
    { id:'p-square-1', start:26.1, end:26.35, device:'dualsense', code:'Square', label:'□', kind:'button', detail:'方块键' },
    { id:'p-cross-2', start:30.6, end:30.95, device:'dualsense', code:'Cross', label:'×', kind:'button', detail:'交叉键' }
  ],
  gaps: [
    {start:10,end:12.8,reason:'已切出目标程序，暂停采集',type:'focus'},
    {start:28.3,end:30.1,reason:'手柄连接中断，未采集到操作',type:'disconnect'}
  ]
};
