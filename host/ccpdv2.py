import time, sys, datetime, os, string
import numpy as np
np.set_printoptions(linewidth="nan", threshold="nan")
import yaml
from basil import dut
import logging
logging.getLogger().setLevel(logging.DEBUG)

#### modules for FEI4
from pybar.run_manager import RunManager
from pybar.scans.scan_init import InitScan
from pybar.scans.scan_ext_trigger import ExtTriggerScan
from pybar.scans.scan_fei4_self_trigger import FEI4SelfTriggerScan
from pybar.scans.tune_threshold_baseline import ThresholdBaselineTuning
import progressbar

class HvcmosScan(ExtTriggerScan):
    '''External trigger scan with FE-I4
    For use with external scintillator (user RX0), TLU (use RJ45), USBpix self-trigger (loop back TX2 into RX0.)
    '''
    _default_run_conf = {
        "trig_count": 0,  # FE-I4 trigger count, number of consecutive BCs, from 0 to 15
        "trigger_mode": 0,  # trigger mode, more details in basil.HL.tlu, from 0 to 3
        "trigger_latency": 232,  # FE-I4 trigger latency, in BCs, external scintillator / TLU / HitOR: 232, USBpix self-trigger: 220
        "trigger_delay": 14,  # trigger delay, in BCs
        "trigger_count": 0,  # consecutive trigger, 0 means 16
        "trigger_rate_limit": 500,  # artificially limiting the trigger rate, in BCs (25ns)
        "trigger_pos_edge": True,  # trigger on the positibe edge of the RX0 trigger signal
        "trigger_time_stamp": False,  # if true trigger number is a time stamp with 40 Mhz clock
        "trigger_tdc": False,  # only create tdc word if it can be assigned to a trigger
        "col_span": [1, 80],#[1,12],
        "row_span": [1, 336], #[184, 208], sn2 [197, 197] [197, 230], #sn3 [219, 219],
        "overwrite_enable_mask": False,
        "use_enable_mask_for_imon": False, 
        "no_data_timeout": 0, #10,
        "scan_timeout": None,   #10,  # in seconds
        "max_triggers": None,
        "enable_tdc": False,
        'reset_rx_on_error': False,  # long scans have a high propability for ESD related data transmission errors; recover and continue here

        "hvcmos_inj":True
        }
    def scan(self):
        # preload command
        lvl1_command = self.register.get_commands("zeros", length=self.trigger_delay)[0] + self.register.get_commands("LV1")[0] + self.register.get_commands("zeros", length=self.trigger_rate_limit)[0]
        self.register_utils.set_command(lvl1_command)

        with self.readout(**self.scan_parameters._asdict()):
            got_data = False
            ### inject to HVCMOS
            if self.hvcmos_inj==True:
                logging.info("inj %s"%self.hvcmos_inj)
                if self.dut['rx']['CCPD_TDC']==1:
                    self.dut['sram'].reset()
                self.dut['CCPD_TDCGATE_PULSE'].start()
            while not self.stop_run.wait(1.0):
                if not got_data:
                    if self.fifo_readout.data_words_per_second() > 0:
                        got_data = True
                        logging.info('Taking data...')
                        self.progressbar = progressbar.ProgressBar(widgets=['', progressbar.Percentage(), ' ', progressbar.Bar(marker='*', left='|', right='|'), ' ', progressbar.AdaptiveETA()], maxval=self.max_triggers, poll=10, term_width=80).start()
                else:
                    triggers = self.dut['tlu']['TRIGGER_COUNTER']
                    try:
                        self.progressbar.update(triggers)
                    except ValueError:
                        pass
                    if self.max_triggers is not None and triggers >= self.max_triggers:
                        self.progressbar.finish()
                        self.stop(msg='Trigger limit was reached: %i' % self.max_triggers)

        logging.info('Total amount of triggers collected: %d', self.dut['tlu']['TRIGGER_COUNTER']) 

class HvcmosSelfScan(FEI4SelfTriggerScan):
    _default_run_conf = {
        "trig_count": 0,  # FE-I4 trigger count, number of consecutive BCs, from 0 to 15
        "trigger_latency": 239,  # FE-I4 trigger latency, in BCs, external scintillator / TLU / HitOR: 232, USBpix self-trigger: 220, from 0 to 255
        "col_span": [1, 80],  # defining active column interval, 2-tuple, from 1 to 80
        "row_span": [1, 336],  # defining active row interval, 2-tuple, from 1 to 336
        "overwrite_enable_mask": False,  # if True, use col_span and row_span to define an active region regardless of the Enable pixel register. If False, use col_span and row_span to define active region by also taking Enable pixel register into account.
        "use_enable_mask_for_imon": False,  # if True, apply inverted Enable pixel mask to Imon pixel mask
        "no_data_timeout": 10,  # no data timeout after which the scan will be aborted, in seconds
        "scan_timeout": 60,  # timeout for scan after which the scan will be stopped, in seconds

        "hvcmos_inj":True        
    }
    def scan(self):
        with self.readout():
            got_data = False
            start = time.time()
            ### inject to HVCMOS
            if self.hvcmos_inj==True:
                logging.info("inj %s"%self.hvcmos_inj)
                if self.dut['rx']['CCPD_TDC']==1:
                    self.dut['sram'].reset()
                self.dut['CCPD_TDCGATE_PULSE'].start()
            while not self.stop_run.wait(1.0):
                if not got_data:
                    if self.fifo_readout.data_words_per_second() > 0:
                        got_data = True
                        logging.info('Taking data...')
                        self.progressbar = progressbar.ProgressBar(widgets=['', progressbar.Percentage(), ' ', progressbar.Bar(marker='*', left='|', right='|'), ' ', progressbar.Timer()], maxval=self.scan_timeout, poll=10, term_width=80).start()
                else:
                    try:
                        self.progressbar.update(time.time() - start)
                    except ValueError:
                        pass

class ccpdv2_logging():
    def __init__(self):
        self.stdout=True
    def set_stdout(self,stdout):
        self.stdout=stdout
    def append(self,output):
        if self.stdout:
            print output
        output=string.join(output.split("\n"),",")
        with open('scan.txt', 'a') as f:
            f.write("%s\n"%output)
    def archive(self):
        with open('scan_archive.txt', 'a') as fo:
            try:
                with open("scan.txt") as f:
                    for line in f:
                        fo.write(line)
                os.remove("scan.txt")
            except:
                pass
            
######### ccpdv2 specific functions
    def output_command(self,cmd):
        self.append("#cmd %s %s"%(time.strftime("%y/%m/%d-%H:%M:%S"),cmd))
    def output_tdacs(self,tdacs,long=True):
        
        notsame=np.argwhere(tdacs!=tdacs[5,49])
        if len(notsame)<15:
            output="#tdacall %d"%tdacs[5,49]
            for n,i in enumerate(notsame):
                output="%s,tdac%d-%d %d"%(output,i[0],i[1],tdacs[i[0],i[1]])
        else:
           output="#tdacall %d"%tdacs[5,49]
           tmp=str(np.asarray(tdacs,int)).split("\n")
           for t in tmp:
              output="%s\n#%s"%(output,t)
        self.append(output)
    def output_gl(self,BLRes,ThRes,VN,VN2,VNFB,VNFoll,VNLoad,VNDAC,
                     ThPRes,ThP,VNOut,VNComp,VNCompLd,VNCOut1,
                     VNCOut2,VNCOut3,VNBuffer,VPFoll,VNBias,
                     EnPullUp,EnPosFB):
        self.append("#BLRes %d,ThRes %d,VN %d,VN2 %d,VNFB %d,VNFoll %d,VNLoad %d,VNDAC %d"%(BLRes,ThRes,VN,VN2,VNFB,VNFoll,VNLoad,VNDAC))
        self.append("#ThPRes %d,ThP %d,VNOut %d,VNComp %d,VNCompLd %d"%(ThPRes,ThP,VNOut,VNComp,VNCompLd))
        self.append("#VNCOut1 %d,VNCOut2 %d,VNCOut3 %d,VNBuffer %d,VPFoll %d,VNBias %d,"%(VNCOut1,VNCOut2,VNCOut3,VNBuffer,VPFoll,VNBias))
        self.append("#VNLoad %d EnPullUp %d,EnPosFB %d"%(VNLoad, EnPullUp, EnPosFB))
    def output_hv(self,hv_v,hv_i):
        self.append("#hv_v %f, hv_i %g"%(hv_v,hv_i))
    def output_en(self,pixels,config):
        self.append("#pixels %s, config %s"%(str(pixels),string.join(config," ")))
    def output_pl(self,repeat,period,delay,en):
        self.append("#repeat %d, period %d, delay %d, inj_en %s"%(repeat,period,delay,str(en)))
    def output_allconfig(self,allconfig):
        output="#allconfig "
        for k in sorted(allconfig.iterkeys()):
            v=allconfig[k]
            if k=="TDACS":
                output="%s\nTDACS %d"%(output,v[5,49])
                for i in np.argwhere(v!=v[5,49]):
                    output="%s,tdac%d-%d %d"%(output,i[0],i[1],v[i[0],i[1]])
            else:
                output="%s\n%s %s"%(output,k, str(v))
        self.append(output)
    def output_configbits(self,bits):
        output="#config"
        for o in bits:
                output="%s\n%s"%(output,o)
        self.append(output)
    def output_globalbits(self,bits):
        output="#global"
        for o in bits:
            output="%s\n%s"%(output,o)
        self.append(output)
    def output_data(self,x,tdc,tdc_std,cnt,all_cnt):
        output="%f %f %f %d %d"%(x,tdc,tdc_std,cnt,all_cnt)
        self.append(output)
    def output_data2(self,x,tdc,tdc_std,cnt,data):
        output="%f %f %f %d %s"%(x,tdc,tdc_std,cnt,str(data))
        self.append(output)
    def output_power(self,dat):
        output="#Vdd %fV(%fmA), Vss %fV(%fmA), VGate %fV(%fmA), Vcasc %fV(%fmA)"%(
                dat["CCPD_Vdd_v"],dat["CCPD_Vdd_i"],dat["CCPD_Vssa_v"],dat["CCPD_Vssa_i"],
                dat["CCPD_VGate_v"],dat["CCPD_VGate_i"],dat["CCPD_Vcasc_v"],dat["CCPD_Vcasc_i"])
        self.append(output)
    def output_th(self,th):
        self.append("#th %f"%th)
    def output_fg(self,low,high):
        self.append("#fg_high %f, fg_low %f"%(high,low))
    def output_pcbth(self,pcbth):
        self.append("#pcbth %f"%pcbth)
    def output_bl(self,bl):
        self.append("#bl %f"%bl)
    def output_inj(self,high,low):
        self.append("#inj_high %f, inj_low %f"%(high,low))
    def output_scope(self,filename):
        self.append("#scope %s"%filename)
    def output_fei4(self,filename):
        self.append("#fei4 %s"%filename)
    def output_mode(self,mode):
        self.append("#mode %s"%mode)
       
class Ccpdv2Fei4():
    def init_with_fei4(self,conf=r"D:\workspace\pybar\branches\development\pybar\configuration.yaml"):
        self.rmg=RunManager(conf)
        self.rmg.run_run(InitScan)
        self.dut=self.rmg.conf["dut"]
        self.init()
    def __init__(self):    
        ### init logging
        self.l=ccpdv2_logging()
        self.dut=None
        
        self.smallhit=100
        self.dataformat=0 # bit0=save h5 file, bit1=save tdc as text, bit4=save to existing file
        self.s=None
        self.hv=5.0
        self.exp=0.0

        ### initial params
        self.BLRes=1
        self.ThRes=20
        self.VN=0
        self.VN2=60
        self.VNFB=1
        self.VNFoll=30
        self.VNLoad=10
        self.VNDAC=10 #6
        self.ThPRes=8
        self.ThP=30
        self.VNOut=50
        self.VNComp=10
        self.VNCompLd=5
        self.VNCOut1=5 #60
        self.VNCOut2=5 #60
        self.VNCOut3=5 #60
        self.VNBuffer=30
        self.VPFoll=30
        self.VNBias=0
        self.EnPullUp=0
        self.EnPosFB=0
        
        self.tdacs=np.zeros([24,60])
        self.enLR=-1
        self.en=1
        self.ao=0  #-1
        self.pixels=[] #[[22,32]]

        self.bl=0.8
        self.th=1.0  #0.85
        self.inj_high=0.75
        self.inj_low=0.5
        self.pcbth=1  #1.90
        self.vss=1.5
        self.vdd=1.8
        self.vcasc=1.0
        self.vgate=2.1
        
        self.repeat=200
        self.period=100
        self.delay=2000
        self.inj_en=True
        self.mode="rj45" #"ccpd"
    def init(self,yamlfile=r"D:\workspace\pybar\branches\development\pybar\ccpdv2.yaml"):
        if self.dut==None:
            self.dut=dut.Dut(yamlfile)
            self.dut.init()

        # reset basil modules
        self.dut['CCPD_GLOBAL'].reset()
        self.dut['CCPD_GLOBAL'].set_size(120)
        self.dut['CCPD_GLOBAL'].set_repeat(1)
        self.dut['CCPD_CONFIG'].reset()
        self.dut['CCPD_CONFIG'].set_repeat(1)
        self.dut['CCPD_CONFIG'].set_size(432)
        self.dut['CCPD_TDC'].reset()
        # config in memory
        self._tdacs=np.ones([24,60])*-1
        self._pixels=[]
        self.debug=0

        self._set(flgs={"hv":0,"gl":1,"t":0,"cnf":1,"th":1,"pl":1,"inj":1,"bl":1,"pcbth":1,
                        "pw":1,"fg":0,"mode":1})     
    def set(self,**kwargs):
        self.l.output_command("set")
        flgs=self._parse(kwargs)
        self._set(flgs)
    def _set(self,flgs):
        if flgs["pw"]!=0:
            self.put_power_on(self.vdd, self.vss, self.vgate, self.vcasc)
            ret=self.get_power()
            self.l.output_power(ret)
        if flgs["inj"]!=0:
            self.put_inj(high=self.inj_high,low=self.inj_low)
            self.l.output_inj(high=self.inj_high,low=self.inj_low)
        if flgs["hv"]!=0:
            self.put_hv(self.hv)
            self.hv,hv_i=self.get_hv()
            self.l.output_hv(self.hv,hv_i)
        if flgs["gl"]!=0:
            self.put_global(BLRes=self.BLRes,ThRes=self.ThRes,VN=self.VN,VN2=self.VN2,VNFB=self.VNFB,VNFoll=self.VNFoll,
                          VNLoad=self.VNLoad,VNDAC=self.VNDAC,ThPRes=self.ThPRes,ThP=self.ThP,VNOut=self.VNOut,
                          VNComp=self.VNComp,VNCompLd=self.VNCompLd,VNCOut1=self.VNCOut1,VNCOut2=self.VNCOut2,
                          VNCOut3=self.VNCOut3,VNBuffer=self.VNBuffer,VPFoll=self.VPFoll,VNBias=self.VNBias,
                          EnPullUp=self.EnPullUp,EnPosFB=self.EnPosFB)
            self.l.output_gl(BLRes=self.BLRes,ThRes=self.ThRes,VN=self.VN,VN2=self.VN2,VNFB=self.VNFB,VNFoll=self.VNFoll,
                          VNLoad=self.VNLoad,VNDAC=self.VNDAC,ThPRes=self.ThPRes,ThP=self.ThP,VNOut=self.VNOut,
                          VNComp=self.VNComp,VNCompLd=self.VNCompLd,VNCOut1=self.VNCOut1,VNCOut2=self.VNCOut2,
                          VNCOut3=self.VNCOut3,VNBuffer=self.VNBuffer,VPFoll=self.VPFoll,VNBias=self.VNBias,
                          EnPullUp=self.EnPullUp,EnPosFB=self.EnPosFB)
        if flgs["t"]!=0:  
            self.put_tdac(self.tdacs)
            self.l.output_tdacs(self.tdacs)
        if flgs["cnf"]!=0:
            self.put_config(self.pixels,en=self.en,ao=self.ao,enLR=self.enLR)
            config=self.get_config()
            self.l.output_en(self.pixels,config)
        if flgs["pl"]!=0:
            self.put_pulser(delay=self.delay,period=self.period,repeat=self.repeat,
                        en=self.inj_en)
            self.l.output_pl(delay=self.delay,period=self.period,repeat=self.repeat,
                        en=self.inj_en)
        if flgs["th"]!=0:
            self.put_th(th=self.th)
            self.l.output_th(th=self.th)
        if flgs["pcbth"]!=0:
            self.put_pcbth(pcbth=self.pcbth)
            self.l.output_pcbth(pcbth=self.pcbth)
        if flgs["bl"]!=0:
            self.put_bl(bl=self.bl)
            self.l.output_bl(bl=self.bl)
        if flgs["mode"]!=0:
            self.put_mode(mode=self.mode)
            self.l.output_mode(mode=self.mode)
    def analyze(self,data):
        data_only=np.bitwise_and(data,0xfff)
        no_noise=data_only[data_only>self.smallhit]
        return np.average(no_noise),np.std(no_noise),len(no_noise),len(data_only),no_noise
    def scan_th(self,start=1.1,stop=0.8,step=-0.01):
        self.l.output_command("scan_th %f %f %f"%(start,stop,step))
        for self.th in np.arange(start,stop,step):
                self.put_th(self.th)
                th=self.get_th()
                data=self.measure(self.exp)
                ### analyze a bit
                tdc,tdc_std,cnt,cnt_all,data=self.analyze(data)
                ### save data
                if (0x2 & self.dataformat)!=0:
                    self.l.output_data2(th,tdc,tdc_std,cnt,data)
                else:
                    self.l.output_data(th,tdc,tdc_std,cnt,cnt_all)
    def set_tdac_again(self):
        self.l.output_command("set_tdac_again")
        self.put_tdac(self.tdacs, True)
    def spectrum(self,n=1):
        self.l.output_command("spectrum %d"%n)
        for i in range(n):
            data=self.measure(self.exp)
            ## analyze a bit
            tdc,tdc_std,cnt,cnt_all,data=self.analyze(data)
                ### save data
            if (0x2 & self.dataformat)!=0:
                    self.l.output_data2(i,tdc,tdc_std,cnt,data)
            else:
                    self.l.output_data(i,tdc,tdc_std,cnt,cnt_all)
    def find_th(self,start=1.3,stop=0.6,step=-0.05):
        self.l.output_command("find_th %f"%step)
        i=0
        th_list=np.arange(start,stop,step)
        while len(th_list)!=i:
            self.th=th_list[i]
            self.put_th(self.th)
            th=self.get_th()
            data=self.measure(self.exp)
            tdc,tdc_std,cnt,cnt_all,data=self.analyze(data)
            self.l.output_data(th,tdc,tdc_std,cnt,cnt_all)
            if abs(step)>abs(-0.05*0.99) and cnt>5:
                print "debug change step to 0.005"
                step=-0.005
                th_list=np.arange(th-9*step,stop,step)
                i=0
            elif abs(step)>abs(-0.005*0.99) and cnt>self.repeat*0.5:
                print "debug change step to 0.001"
                step=-0.001
                th_list=np.arange(th-6*step,stop,step)
                i=0
            elif abs(step)>abs(-0.001*0.99) and  cnt> self.repeat*0.6:
                break
            else:
                i=i+1
    def find_noise(self,start=1.1,stop=0.6,step=-0.05,exp=0.01):
        self.l.output_command("find_noise %f"%step)
        ### init
        th_list=np.arange(start,stop,step)
        self.exp=exp
        i=0
        state="first"
        while len(th_list)!=i:
            if self.debug==1:
                print i,th_list[0:10]
            self.th=th_list[i]
            self.put_th(th=self.th)
            #th=self.get_th()
            th=self.th
            data=self.measure(self.exp)
            tdc,tdc_std,cnt,cnt_all,data=self.analyze(data)
            if (self.dataformat & 0x2)!=0:
                self.l.output_data2(th,tdc,tdc_std,cnt,data)
            else:
                self.l.output_data(th,tdc,tdc_std,cnt,cnt_all)
            ### find next step
            if cnt_all!=0 and (state=="first" or state=="again") and i==0:
                if self.debug==1:
                    print "go back %s"%state
                th_list=np.arange(th-10*step,stop,step)
            elif state=="first" and i==len(th_list)-1:
                step=step*0.5
                th_list=np.arange(start,stop,step)
                state="again"
                i=0
            elif cnt_all!=0 and (state=="first" or state=="again") and i!=0:
                state= "2midium"
                if self.debug==1:
                    print state
                step=-0.005
                th_list=np.arange(th-9*step,stop,step)
                i=0
            elif cnt_all!=0 and state=="2midium" and i==0:
                state="2midium"
                if self.debug==1:
                    print "go back %s"%state
                th_list=np.arange(th-9*step,stop,step)
                i=0
            elif cnt_all!=0 and state=="2midium" and i!=0:
                state="3exp"
                if self.debug==1:
                    print state
                self.exp=exp*10
                th_list=np.arange(th-9*step,stop,step)
                i=0
            elif cnt_all!=0 and state=="3exp" and i==0:
                if self.debug==1:
                    print "go back2 %s"%state
                th_list=np.arange(th-9*step,stop,step)
                i=0
            elif cnt_all!=0 and state=="3exp" and i!=0:
                state="4small"
                if self.debug==1:
                    print state
                step=-0.001
                th_list=np.arange(th-4*step,stop,step)
                i=0
            elif cnt_all!=0 and state=="3exp" and i==0:
                if self.debug==1:
                    print state
                th_list=np.arange(th-4*step,stop,step)
            elif cnt_all>5 and state=="4small" and i!=0:
                self.l.append("#noise th %f"%th)
                break
            else:
                i=i+1
        return th
    def find_tdac(self,cnt_th=5,exp=0.1):
        self.l.output_command("find_noise %f"%exp)
        self.exp=exp
        for t in range(0,16):
            ## set new tdac
            for p in self.pixels:
                self.tdacs[p[0],p[1]]=t
            self.put_tdac(self.tdacs)
            self.l.output_tdacs(self.tdacs,long=False)
            self.put_config(self.pixels,en=self.en,ao=self.ao,enLR=self.enLR)
            self.l.output_en(self.pixels,[])
            ## measure
            data=self.measure(self.exp)
            tdc,tdc_std,cnt,cnt_all,data=self.analyze(data)
            ### save data
            if (0x2 & self.dataformat)!=0:
                self.l.output_data2(self.th,tdc,tdc_std,cnt,data)
            else:
                self.l.output_data(self.th,tdc,tdc_std,cnt,cnt_all)
            ### next step
            if cnt_all>cnt_th:
                if t!=0:
                    for p in self.pixels:
                        self.tdacs[p[0],p[1]]=t-1
                    self.put_tdac(self.tdacs)
                    self.l.output_tdacs(self.tdacs,long=False)
                self.l.append("#found tdac %d"%(t-1))
                break
            elif t==15:
                self.l.append("#found tdac out of range")
    def clear(self):
        self.l.archive()
    def show(self):
        self.l.output_command("show")
        allconfig=self.get_allconfig()
        allconfig["inj_high"]=self.inj_high
        allconfig["inj_low"]=self.inj_low
        self.l.output_allconfig(allconfig)
    def show2(self):
        self.l.output_command("show2")
        bits=self.get_config()
        self.l.output_configbits(bits)
        bits=self.get_global()
        self.l.output_globalbits(bits)
    def _parse(self,kwargs):
        flgs={"hv":0,"gl":0,"t":0,"cnf":0,"fg":0,"pl":0,"inj":0,"th":0,"bl":0,"pcbth":0,"pw":0,"fg":0,"mode":0}
        for k,v in kwargs.iteritems():
            ### global
            if k=="EnPosFB":
              self.EnPosFB=v
              flgs["gl"]=1
            elif k=="EnPullUp":
              self.EnPullUp=v
              flgs["gl"]=1
            elif k=="VNBias":
              self.VNBias=v
              flgs["gl"]=1
            elif k=="VPFoll":
              self.VPFoll=v
              flgs["gl"]=1
            elif k=="VNBuffer":
              self.VNBuffer=v
              flgs["gl"]=1
            elif k=="VNDAC":
              self.VNDAC=v
              flgs["gl"]=1
            elif k=="VNCOut1":
              self.VNCOut1=v
              flgs["gl"]=1
            elif k=="VNCOut2":
              self.VNCOut2=v
              flgs["gl"]=1
            elif k=="VNCOut3":
              self.VNCOut3=v
              flgs["gl"]=1
            elif k=="VNComp":
              self.VNComp=v
              flgs["gl"]=1
            elif k=="VNCompLd":
              self.VNCompLd=v
              flgs["gl"]=1
            elif k=="VNOut":
              self.VNOut=v
              flgs["gl"]=1
            elif k=="ThP":
              self.ThP=v
              flgs["gl"]=1
            elif k=="ThPRes":
              self.ThPRes=v
              flgs["gl"]=1
            elif k=="VNLoad":
              self.VNLoad=v
              flgs["gl"]=1
            elif k=="VNFoll":
              self.VNFoll=v
              flgs["gl"]=1
            elif k=="VNFB":
              self.VNFB=v
              flgs["gl"]=1
            elif k=="VN2":
              self.VN2=v
              flgs["gl"]=1
            elif k=="VN":
              self.VN=v
              flgs["gl"]=1
            elif k=="BLRes":
              self.BLRes=v
              flgs["gl"]=1
            elif k=="ThRes":
              self.ThRes=v
              flgs["gl"]=1
            ### other parameters
            elif k=="exp":
                self.exp=v
            elif k=="smallhit":
                self.smallhit=v
            elif k=="dataformat":
                self.dataformat=v
            #### config
            elif k=="pixels" or k=="pix":
                if isinstance(v,type("")):
                    if v=="all":
                        self.pixels=[]
                        for i in range(60):
                            for j in range(24):
                                self.pixels.append([j,i])
                    elif v=="std":
                        self.pixels=[]
                        for i in range(12,48):
                            for j in range(24):
                                self.pixels.append([j,i])
                    elif v=="none":
                        self.pixels=[]
                elif isinstance(v[0],int):
                    self.pixels=[v]
                else:
                    self.pixels=v
                flgs["cnf"]=1
            elif k=="enLR":
                self.enLR=v
                flgs["cnf"]=1
            elif k=="ao":
                self.ao=v
                flgs["cnf"]=1
            elif k=="en":
                self.en=v
                flgs["cnf"]=1
            #### pulser
            elif k=="inj_en":
                self.inj_en=v
                flgs["pl"]=1
            elif k=="delay":
                self.delay=v
                flgs["pl"]=1
            elif k=="period":
                self.period=v
                flgs["pl"]=1
            elif k=="repeat":
                self.repeat=v
                flgs["pl"]=1
            #### tdacs
            elif "tdac" in k:
                flgs["t"]=1
                flgs["cnf"]=1
                if isinstance(v,type("")):
                    tmp=np.loadtxt(v)
                    for t in tmp:
                        self.tdacs[t[0],t[1]]=t[2]
                elif isinstance(v,type(self.tdacs)):
                    self.tdacs=v
                elif k[4:]=="all":
                    self.tdacs=self.tdacs*0+v
                    if kwargs.has_key("tdacmonpix"):
                        if kwargs.has_key("pixels"):
                            col = kwargs["pixels"][0][1]
                            row = kwargs["pixels"][0][0]
                        else:
                            col=self.pixels[0][1]
                            row=self.pixels[0][0]
                        self.tdacs[row,col]=kwargs["tdacmonpix"]
                elif k[4:]=="monpix":
                    if not kwargs.has_key("tdacall"):
                        if kwargs.has_key("pixels"):
                            col = kwargs["pixels"][0][1]
                            row = kwargs["pixels"][0][0]
                        else:
                            col=self.pixels[0][1]
                            row=self.pixels[0][0]
                        self.tdacs[row,col]=v
                else:
                    x,y=k[4:].split("_")
                    self.tdacs[string.atoi(x),string.atoi(y)]=v
            ### inj th bl
            elif k=='pcbth':
                self.pcbth=v
                flgs['pcbth']=1
            elif k=='bl' or k=='BL':
                self.bl=v
                flgs['bl']=1
            elif k=='th':
                self.th=v
                flgs['th']=1
            elif k=='inj_high':
                self.inj_high=v
                flgs['inj']=1
            elif k=='inj_low':
                self.inj_low=v
                flgs['inj']=1
            elif k=='hv':
                self.hv=v
                flgs['hv']=1
            elif k=='vdd':
                self.vdd=v
                flgs['pw']=1
            elif k=='vss':
                self.vss=v
                flgs['pw']=1
            elif k=='vcasc':
                self.vcasc=v
                flgs['pw']=1
            elif k=='vgate':
                self.vgate=v
                flgs['pw']=1
            elif k=='mode':
                self.mode=v
                flgs['mode']=1
            else:
                print "invalid param"
                raise ValueError("invalid param %s"%k)
        return flgs
    def set_debug(self,debug):
        self.debug=debug          
    def put_power_on(self,vdd,vss,vgate,vcasc):
            retry=5
            self.dut["CCPD_Vdd"].set_current_limit(200, unit="mA")
            vset=vdd
            self.dut["CCPD_Vdd"].set_voltage(value=vset,unit="V")
            self.dut['CCPD_Vdd'].set_enable(True)
            # for i in range(5):
                # v=self.dut["CCPD_Vdd"].get_voltage(unit="V")
                # oc=self.dut["CCPD_Vdd"].get_over_current()
                # if self.debug==1:
                    # i=self.dut["CCPD_Vssa"].get_current(unit="mA")
                    # print "Vssa: %fV(%fmA),oc="%(v,i),oc
                # if oc==True:
                    # print "ERR CCPD_Vdd over current %fV"%v
                    # raise ValueError("ERR CCPD_Vdd over current %fV"%v)
                # elif v>vset*0.9 and v<vset*1.1:
                    # break
                # elif v>vset*1.1:
                    # self.dut['CCPD_Vdd'].set_enable(False)
                    # self.dut["CCPD_Vdd"].set_voltage(0.8,unit="V")
                    # raise ValueError("ERR CCPD_Vdd voltage %fV"%v)
                # else:
                    # print "CCPD_Vdd=%fV, Retry.."%(v)
                    # self.dut["CCPD_Vdd"].set_voltage(value=vset,unit="V")
                    # self.dut['CCPD_Vdd'].set_enable(True)
            # if i==retry-1:
                # pass
                # #raise ValueError("ERR CCPD_Vdd voltage %fV"%v)
            time.sleep(1)

            vset=vss
            self.dut["CCPD_Vssa"].set_voltage(value=vset,unit="V")
            self.dut['CCPD_Vssa'].set_enable(True)
            # for i in range(5):
                # v=self.dut["CCPD_Vssa"].get_voltage(unit="V")
                # oc=self.dut["CCPD_Vssa"].get_over_current()
                # if self.debug==1:
                    # i=self.dut["CCPD_Vssa"].get_current(unit="mA")
                    # print "Vssa: %fV(%fmA),oc="%(v,i),oc
                # if oc==True:
                    # print "ERR CCPD_Vssa voltage %fV"%v
                # elif v>vset*0.9 and v<vset*1.1:
                    # break
                # elif v>vset*1.1:
                    # self.dut['CCPD_Vssa'].set_enable(False)
                    # self.dut["CCPD_Vssa"].set_voltage(0.8,unit="V")
                    # print "ERR CCPD_Vssa voltage"%v
                # else:
                    # print "CCPD_Vssa=%fV, Retry %d.."%(v,i)
                    # self.dut["CCPD_Vssa"].set_voltage(value=vset,unit="V")
                    # self.dut['CCPD_Vssa'].set_enable(True)
            # if i==retry-1:
                # pass
                # #raise ValueError("ERR CCPD_Vssa voltage %fV"%v)

            vset=vgate
            self.dut["CCPD_VGate"].set_voltage(value=vset,unit="V")
            self.dut['CCPD_VGate'].set_enable(True)
            # for i in range(5):
                # v=self.dut["CCPD_VGate"].get_voltage(unit="V")
                # oc=self.dut["CCPD_VGate"].get_over_current()
                # if self.debug==1:
                    # i=self.dut["CCPD_VGate"].get_current(unit="mA")
                    # print "Gate: %fV(%fmA),oc="%(v,i),oc
                # if oc==True:
                    # print "ERR CCPD_VGate over current %fV"%v
                # elif v>vset*0.9 and v<vset*1.1:
                    # break
                # elif v>vset*1.1:
                    # self.dut['CCPD_VGate'].set_enable(False)
                    # self.dut["CCPD_VGate"].set_voltage(0.8,unit="V")
                    # print "ERR CCPD_VGate voltage %fV"%v
                # else:
                    # print "CCPD_VGate=%fV, Retry.."%(v)
                    # self.dut["CCPD_VGate"].set_voltage(value=vset,unit="V")
                    # self.dut['CCPD_VGate'].set_enable(True)
            # if i==retry-1:
                # pass
                # #raise ValueError("ERR CCPD_VGate voltage %fV"%v)

            self.dut["CCPD_Vcasc"].set_voltage(value=vcasc,unit="V")
            if self.debug==1:
                print "Vcasc",self.dut["CCPD_Vcasc"].get_voltage(unit="V"),"V (",
                print self.dut["CCPD_Vcasc"].get_current(unit="mA"),"mA)"
    def put_power_off(self):
            self.dut["CCPD_Vcasc"].set_voltage(value=0,unit="V")
            self.dut["CCPD_BL"].set_voltage(value=0,unit="V")
            self.dut["CCPD_Th"].set_voltage(value=0,unit="V")
            self.dut["PCB_Th"].set_voltage(value=0,unit="V")
            self.dut['CCPD_Vssa'].set_enable(False)
            self.dut['CCPD_VGate'].set_enable(False)
            time.sleep(1)
            self.dut['CCPD_Vdd'].set_enable(False)
    def get_power(self):
        ret={}
        ret["CCPD_Vdd_v"]=self.dut["CCPD_Vdd"].get_voltage(unit="V")
        ret["CCPD_Vdd_i"]=self.dut["CCPD_Vdd"].get_current(unit="mA")
        ret["CCPD_Vssa_v"]=self.dut["CCPD_Vssa"].get_voltage(unit="V")
        ret["CCPD_Vssa_i"]=self.dut["CCPD_Vssa"].get_current(unit="mA")
        ret["CCPD_VGate_v"]=self.dut["CCPD_VGate"].get_voltage(unit="V")
        ret["CCPD_VGate_i"]=self.dut["CCPD_VGate"].get_current(unit="mA")
        ret["CCPD_Vcasc_v"]=self.dut["CCPD_Vcasc"].get_voltage(unit="V")
        ret["CCPD_Vcasc_i"]=self.dut["CCPD_Vcasc"].get_current(unit="mA")
        return ret
    def put_hv(self,hv):
        hv=-hv
        if hv<0:
            print "Ccpdv2Gpac.put_hv() HV must be negative"
            return
        self.dut["HV"].debug=1
        self.dut["HV"].set_voltage(value=hv,unit="V")    
    def get_hv(self):
        hv=self.dut["HV"].get_voltage(unit="V")
        hv_i=self.dut["HV"].get_current(unit="A")
        return hv, hv_i
    def _write_reg(self,register_name):
        if self.debug==1:
            print self.dut[register_name]
        self.dut[register_name].write()
        self.dut[register_name].start()
        if self.dut[register_name].get_repeat()==0:
            return
        for i in range(1000000):
            if self.dut[register_name].is_done():
                break
            if i > 100:
                time.sleep(0.001)  # avoid "CPU 100%"
        if i==1000000-1:
            print "Ccpdv2._write_reg()Timeout"
    def get_data(self):
        for i in range(10000):
            #print i,self.dut['CCPD_TDCGATE_PULSE'].is_done()
            if self.dut['CCPD_TDCGATE_PULSE'].is_done():
                break
            if i > 100:
                time.sleep(0.001)  # avoid "CPU 100%"
        if i==10000-1:
            print "Ccpdv2.get_data()Timeout"
        return self.dut['sram'].get_data()
    def get_data_now(self):
        return self.dut['sram'].get_data()
    def put_tdac(self,tdacs,force_reload=False,vdd=True):
        if self.debug==1:
            v=self.dut["CCPD_Vdd"].get_voltage(unit="V")
            i=self.dut["CCPD_Vdd"].get_current(unit="mA")
            print "put_tdac: initial Vdd %fV(%fmA)...."%(v,i)
            t=time.time()
        if vdd==True:
            self.dut["CCPD_Vdd"].set_voltage(value=1.999,unit="V")
        if self.debug==1 or self.debug==0:
            v=self.dut["CCPD_Vdd"].get_voltage(unit="V")
            i=self.dut["CCPD_Vdd"].get_current(unit="mA")
            print "+++++++++++put_tdac: Vdd during TDAC update %fV(%fmA)...."%(v,i),
        if force_reload==True:
            cols=np.arange(0,60,1)
        else:
            cols=np.unique(np.where(self._tdacs!=tdacs)[1])
        for col in cols:
            wr="Ld%d"%(col%3)
            for row in range(24):
                if row%4==1 or row%4==2:
                    indac="InL"
                elif row%4==0 or row%4==3:
                    indac="InR"
                if self.debug>1:
                    print row,col,tdacs
                self.dut['CCPD_CONFIG']['ROW'][11-row/2][indac] = int(tdacs[row,col])
            for i in range(5):
                self.dut['CCPD_CONFIG']['COLUMN'][19-col/3][wr] = 0
                self._write_reg('CCPD_CONFIG')
                self.dut['CCPD_CONFIG']['COLUMN'][19-col/3][wr] = 1
                self._write_reg('CCPD_CONFIG')
                self.dut['CCPD_CONFIG']['COLUMN'][19-col/3][wr] = 0
        if self.debug==1:
            v=self.dut["CCPD_Vdd"].get_voltage(unit="V")
            i=self.dut["CCPD_Vdd"].get_current(unit="mA")
            print "put_tdac: Vdd %fV(%fmA) time: %fs"%(v,i,time.time()-t)
        self.dut["CCPD_Vdd"].set_voltage(value=1.8,unit="V")
        if self.debug==1 or self.debug==0:
            v=self.dut["CCPD_Vdd"].get_voltage(unit="V")
            i=self.dut["CCPD_Vdd"].get_current(unit="mA")
            print "put_tdac: Vdd during TDAC update %fV(%fmA)+++++++++++"%(v,i)
        self._tdacs=np.copy(tdacs) ##TODO keep tdacs in memory. this should be done by get_data() 
    def _config_monitor(self, pixels, enLR):
        #disable all pixels
        for i in range(0,12):
            self.dut['CCPD_CONFIG']['ROW'][i]['EnL'] = 1
            self.dut['CCPD_CONFIG']['ROW'][i]['EnR'] = 1
        for i in range(0,20):
            self.dut['CCPD_CONFIG']['COLUMN'][i]["L0"] = 0
            self.dut['CCPD_CONFIG']['COLUMN'][i]["R0"] = 0
            self.dut['CCPD_CONFIG']['COLUMN'][i]["L1"] = 0
            self.dut['CCPD_CONFIG']['COLUMN'][i]["R1"] = 0
            self.dut['CCPD_CONFIG']['COLUMN'][i]["L2"] = 0
            self.dut['CCPD_CONFIG']['COLUMN'][i]["R2"] = 0
        for p in pixels:
            row=p[0]
            col=p[1]
            if row%4==0 or row%4==3:
                enLR_idx="EnR"
            elif row%4==1 or row%4==2:
                enLR_idx="EnL"
            if row%4==0 or row%4==2:
                lr_idx="L"
            elif row%4==1 or row%4==3:
                lr_idx="R"
            lr_idx="%s%d"%(lr_idx,col%3)
            self.dut['CCPD_CONFIG']['ROW'][11-(row/2)][enLR_idx] = 0
            self.dut['CCPD_CONFIG']['COLUMN'][19-(col/3)][lr_idx] = 1
            if self.debug==1:
                print "ROW",11-(row/2),"enLR",enLR_idx,"COL",19-(col/3),"lr",lr_idx
        if enLR!=-1:
            enLR=format(enLR,"024b")
            for row,e in enumerate(enLR):
                v=string.atoi(e)
                if row%4==1 or row%4==2:
                    enLR_idx="EnL"
                elif row%4==0 or row%4==3:
                    enLR_idx="EnR"
                self.dut['CCPD_CONFIG']['ROW'][11-(row/2)][enLR_idx] = int(v)
    def _config_preamp(self,en):
        if isinstance(en,int):
            for i in range(12):
                    if en==1:
                        self.dut['CCPD_CONFIG']['ROW'][i]['En0'] = 1
                        self.dut['CCPD_CONFIG']['ROW'][i]['En1'] = 1
                        self.dut['CCPD_CONFIG']['ROW'][i]['En2'] = 1
                        self.dut['CCPD_CONFIG']['ROW'][i]['En3'] = 1
                        self.dut['CCPD_CONFIG']['ROW'][i]['En4'] = 1
                        self.dut['CCPD_CONFIG']['ROW'][i]['En5'] = 1
                    else:
                        self.dut['CCPD_CONFIG']['ROW'][i]['En0'] = 0
                        self.dut['CCPD_CONFIG']['ROW'][i]['En1'] = 0
                        self.dut['CCPD_CONFIG']['ROW'][i]['En2'] = 0
                        self.dut['CCPD_CONFIG']['ROW'][i]['En3'] = 0
                        self.dut['CCPD_CONFIG']['ROW'][i]['En4'] = 0
                        self.dut['CCPD_CONFIG']['ROW'][i]['En5'] = 0
            for p in self._pixels:
                row=p[0]
                col=p[1]
                if (row%4==1 and col%3==0) or (row%4==2 and col%3==0):
                    en = "En0"
                elif (row%4==1 and col%3==1) or (row%4==2 and col%3==1):
                    en = "En1"
                elif (row%4==1 and col%3==2) or (row%4==2 and col%3==2):
                    en = "En2"
                elif (row%4==0 and col%3==0) or (row%4==3 and col%3==0):
                    en = "En3"
                elif (row%4==0 and col%3==1) or (row%4==3 and col%3==1):
                    en = "En4"
                elif (row%4==0 and col%3==2) or (row%4==3 and col%3==2):
                    en = "En5"
                self.dut['CCPD_CONFIG']['ROW'][11-(row/2)][en]=1 
        elif isinstance(en,type([])):
            en_i=format(en[0],"024b")
            for row,e in enumerate(en_i):
                v=string.atoi(e)
                if row%4==1 or row%4==2:
                    bit="En0"
                elif row%4==0 or row%4==3:
                    bit="En3"
                self.dut['CCPD_CONFIG']['ROW'][11-(row/2)][bit] = int(v)
            en_i=format(en[1],"024b")
            for row,e in enumerate(en_i):
                v=string.atoi(e)
                if row%4==1 or row%4==2:
                    bit="En1"
                elif row%4==0 or row%4==3:
                    bit="En4"
                self.dut['CCPD_CONFIG']['ROW'][11-(row/2)][bit] = int(v)
            en_i=format(en[2],"024b")
            for row,e in enumerate(en_i):
                v=string.atoi(e)
                if row%4==1 or row%4==2:
                    bit="En2"
                elif row%4==0 or row%4==3:
                    bit="En5"
                self.dut['CCPD_CONFIG']['ROW'][11-(row/2)][bit] = int(v)                 
    def _config_ao(self,ao):
        for i in range(20):
            self.dut['CCPD_CONFIG']['COLUMN'][i]["ao"] = 0 
        if ao==0:
            pass
        elif ao==-1:
            for p in self._pixels:
                col=p[1]
                self.dut['CCPD_CONFIG']['COLUMN'][19-(col/3)]["ao"] = 1
        else:          
            ao=format(ao,"020b")
            for i,e in enumerate(ao):
                v=string.atoi(e)
                self.dut['CCPD_CONFIG']['COLUMN'][19-i]["ao"] = int(v) ### here col=i*3
    def put_config(self,pixels,en,ao,enLR):
        self._pixels=pixels
        self._config_monitor(pixels, enLR)
        self._config_preamp(en)
        self._config_ao(ao)
        self._write_reg("CCPD_CONFIG")
    def start_pulser(self):
        if self.dut['rx']['CCPD_TDC']==1:
            self.dut['sram'].reset()
        self.dut['CCPD_TDCGATE_PULSE'].start()
    def put_th(self,th):
        if th>1.999 or th<-0.1:
            raise ValueError("invalid voltage for TH %f"%th)
        self.dut["CCPD_Th"].set_voltage(value=th,unit="V")
    def get_th(self,with_current=False):
        th=self.dut["CCPD_Th"].get_voltage(unit="V")
        if with_current==True:
            th_i=self.dut["CCPD_Th"].get_current(unit="mA")
            return th,th_i
        else:
            return th
    def put_pcbth(self,pcbth):
        self.dut["PCB_Th"].set_voltage(value=pcbth,unit="V")
    def get_pcbth(self,with_current=False):
        pcbth=self.dut["PCB_Th"].get_voltage(unit="V")
        if with_current==True:
            pcbth_i=self.dut["PCB_Th"].get_current(unit="mA")
            return pcbth,pcbth_i
        else:
            return pcbth
    def put_bl(self,bl):
        if bl>1.9 or bl<-0.1:
            raise ValueError("invalid voltage for BL")
        self.dut["CCPD_BL"].set_voltage(value=bl,unit="V")
    def get_bl(self,with_current=False):
        bl=self.dut["CCPD_BL"].get_voltage(unit="V")
        if with_current==True:
            bl_i=self.dut["CCPD_BL"].get_current(unit="mA")
            return bl,bl_i
        else:
            return bl
    def put_inj(self,high,low):
        self.dut['CCPD_Injection_high'].set_voltage(value=high,unit="V")
        self.dut['CCPD_Injection_low'].set_voltage(value=low,unit="V")
    def get_inj(self,with_current=False):
        high=self.dut['CCPD_Injection_high'].get_voltage(unit="V")
        low=self.dut['CCPD_Injection_low'].get_voltage(unit="V")
        if with_current==True:
            high_i=self.dut['CCPD_Injection_high'].get_current(unit="mA")
            low_i=self.dut['CCPD_Injection_low'].get_current(unit="mA")
            return high,low,high_i,low_i
        else:
            return high,low
    def put_pulser(self,delay,period,repeat,en):
        if repeat==0:
            self.dut['CCPD_INJ_PULSE'].reset()
            self.dut['CCPD_INJ_PULSE'].set_delay(10)
            self.dut['CCPD_INJ_PULSE'].set_width(period/2)
            self.dut['CCPD_INJ_PULSE'].set_repeat(1)
            self.dut['CCPD_INJ_PULSE'].set_en(en) 
            self.dut['CCPD_TDCGATE_PULSE'].reset()
            self.dut['CCPD_TDCGATE_PULSE'].set_delay(10)
            self.dut['CCPD_TDCGATE_PULSE'].set_width(100)
            self.dut['CCPD_TDCGATE_PULSE'].set_repeat(1)
            self.dut['CCPD_TDCGATE_PULSE'].set_en(True)
            if self.dut['rx']['CCPD_TDC']==1:
                self.dut['sram'].reset()
            self.dut['CCPD_TDC'].reset()
            self.dut['CCPD_TDC'].set_en_extern(0)
        else:
            self.dut['CCPD_INJ_PULSE'].reset()
            self.dut['CCPD_INJ_PULSE'].set_delay(period/2)
            self.dut['CCPD_INJ_PULSE'].set_width(period-period/2+1)
            self.dut['CCPD_INJ_PULSE'].set_repeat(repeat)
            self.dut['CCPD_INJ_PULSE'].set_en(en)
            self.dut['CCPD_TDCGATE_PULSE'].reset()
            self.dut['CCPD_TDCGATE_PULSE'].set_delay(delay)
            self.dut['CCPD_TDCGATE_PULSE'].set_width((period+1)*(repeat+1))
            self.dut['CCPD_TDCGATE_PULSE'].set_repeat(1)
            self.dut['CCPD_TDCGATE_PULSE'].set_en(True)
            self.dut['CCPD_TDC'].reset()
            self.dut['CCPD_TDC'].set_en_extern(True)
            if self.dut['rx']['CCPD_TDC']==1:
                self.dut['sram'].reset()
    def put_mode(self,mode):
        self.dut['sram'].reset()
        self.dut['rx'].reset()
        if mode=="ccpd":
            self.dut['rx']['FE'] = 0
            self.dut['rx']['TLU'] = 0
            self.dut['rx']['TDC'] = 0
            self.dut['rx']['CCPD_TDC'] = 1
            self.dut['rx']['HITMON_SEL'] = 0 
            self.dut['rx']['EX_SEL'] = 0            
        elif mode=="hitmon":
            self.dut['rx']['FE'] = 1
            self.dut['rx']['TLU'] = 1
            self.dut['rx']['TDC'] = 1
            self.dut['rx']['CCPD_TDC'] = 0
            self.dut['rx']['HITMON_SEL'] = 1 
            self.dut['rx']['EX_SEL'] = 1
        elif mode=="inj":
            self.dut['rx']['FE'] = 1
            self.dut['rx']['TLU'] = 1
            self.dut['rx']['TDC'] = 1
            self.dut['rx']['CCPD_TDC'] = 0
            self.dut['rx']['HITMON_SEL'] = 0 
            self.dut['rx']['EX_SEL'] = 1
        elif mode=="lemo" or mode=="rj45":
            self.dut['rx']['FE'] = 1
            self.dut['rx']['TLU'] = 1
            self.dut['rx']['TDC'] = 1
            self.dut['rx']['CCPD_TDC'] = 0
            self.dut['rx']['HITMON_SEL'] = 0 
            self.dut['rx']['EX_SEL'] = 0
        else:
            raise  ValueError("invalid mode %s, ccpd,hitmon,inj,lemo(rj45)"%mode)
        self.dut['rx'].write()  
    def put_global(self,BLRes,ThRes,VN,VN2,VNFB,VNFoll,VNLoad,VNDAC,
                   ThPRes,ThP,VNOut,VNComp,VNCompLd,VNCOut1,VNCOut2,VNCOut3,
                   VNBuffer,VPFoll,VNBias,EnPullUp,EnPosFB):
        self.dut['CCPD_GLOBAL']['EnPosFB'] = EnPosFB
        self.dut['CCPD_GLOBAL']['EnPullUp'] = EnPullUp
        self.dut['CCPD_GLOBAL']['VPFoll'] = VPFoll
        self.dut['CCPD_GLOBAL']['VNBuffer'] = VNBuffer
        self.dut['CCPD_GLOBAL']['VNCOut3'] = VNCOut3
        self.dut['CCPD_GLOBAL']['VNCOut2'] = VNCOut2
        self.dut['CCPD_GLOBAL']['VNCOut1'] = VNCOut1
        self.dut['CCPD_GLOBAL']['VNCompLd'] = VNCompLd
        self.dut['CCPD_GLOBAL']['VNComp'] = VNComp
        self.dut['CCPD_GLOBAL']['VNOut'] = VNOut
        self.dut['CCPD_GLOBAL']['ThPRes'] = ThPRes
        self.dut['CCPD_GLOBAL']['ThP'] = ThP
        self.dut['CCPD_GLOBAL']['VNDAC'] = VNDAC
        self.dut['CCPD_GLOBAL']['VNLoad'] = VNLoad
        self.dut['CCPD_GLOBAL']['VNFoll'] = VNFoll
        self.dut['CCPD_GLOBAL']['VNFB'] = VNFB
        self.dut['CCPD_GLOBAL']['VN2'] = VN2
        self.dut['CCPD_GLOBAL']['VN'] = VN
        self.dut['CCPD_GLOBAL']['ThRes'] = ThRes
        self.dut['CCPD_GLOBAL']['BLRes'] = BLRes
        self._write_reg("CCPD_GLOBAL")
    def get_config(self):
        dat= str(self.dut['CCPD_CONFIG']).split("'")[3][4:]
        ret=[]
        i=0
        for j in range(12):
            ret.append(dat[i:i+16])
            i=i+16
        for j in range(20):
            ret.append(dat[i:i+12])
            i=i+12
        return ret
    def get_global(self):
        dat= str(self.dut['CCPD_GLOBAL']).split("'")[3][4:]
        ret=[]
        for j in range(20):
            #v=dat[j*6+0]+dat[j*6+1]+dat[j*6+2]+dat[j*6+5]+dat[j*6+3]+dat[j*6+4]
            ret.append(dat[j*6:(j+1)*6])
        return ret
    def _int_global(self,gl):
        tmp=str(self.dut['CCPD_GLOBAL'][gl])
        v=tmp[5]+tmp[4]+tmp[3]+tmp[0]+tmp[2]+tmp[1]
        return int(v,2)
    def get_allconfig(self):
        ## TODO: this data should be from get_data()
        return {'BLRes': self._int_global('BLRes'),
          'ThRes': self._int_global('ThRes'),
          'VN': self._int_global('VN'),
          'VN2': self._int_global('VN2'),
          'VNFB': self._int_global('VNFB'),
          'VNFoll': self._int_global('VNFoll'),
          'VNLoad': self._int_global('VNLoad'),
          'VNDAC': self._int_global('VNDAC'),
          'ThPRes': self._int_global('ThPRes'),
          'ThP': self._int_global('ThP'),
          'VNOut': self._int_global('VNOut'),
          'VNComp': self._int_global('VNComp'),
          'VNCompLd': self._int_global('VNCompLd'),
          'VNCOut1': self._int_global('VNCOut1'),
          'VNCOut2': self._int_global('VNCOut2'),
          'VNCOut3': self._int_global('VNCOut3'),
          'VNBuffer': self._int_global('VNBuffer'),
          'VPFoll': self._int_global('VPFoll'),        
          'VNBias': self._int_global('VNBias'),
          'EnPullUp': int(str(self.dut['CCPD_GLOBAL']['EnPullUp']),2),
          'EnPosFB': int(str(self.dut['CCPD_GLOBAL']['EnPosFB']),2),
          'TDCGATE_delay': self.dut['CCPD_TDCGATE_PULSE'].get_delay(),
          'TDCGATE_width': self.dut['CCPD_TDCGATE_PULSE'].get_width(),
          'TDCGATE_repeat': self.dut['CCPD_TDCGATE_PULSE'].get_repeat(),
          'TDCGATE_en': self.dut['CCPD_TDCGATE_PULSE'].get_en(),
          'INJ_delay': self.dut['CCPD_INJ_PULSE'].get_delay(),
          'INJ_width': self.dut['CCPD_INJ_PULSE'].get_width(),
          'INJ_repeat': self.dut['CCPD_INJ_PULSE'].get_repeat(),
          'INJ_en': self.dut['CCPD_INJ_PULSE'].get_en(),
          'TDC_en': self.dut['CCPD_TDC'].get_en(),
          'TDC_en_extern': self.dut['CCPD_TDC'].get_en_extern(),
          'TDACS': self.tdacs,
          'pixels': self.pixels,
          'CCPD_CONFIG':str(self.dut['CCPD_CONFIG']).split("'")[3][4:],
          'Vdd_v':self.dut["CCPD_Vdd"].get_voltage(unit="V"),
          'Vdd_i':self.dut["CCPD_Vdd"].get_current(unit="mA"),
          'Vssa_v':self.dut["CCPD_Vssa"].get_voltage(unit="V"),
          'Vssa_i':self.dut["CCPD_Vssa"].get_current(unit="mA"),
          'VGate_v':self.dut["CCPD_VGate"].get_voltage(unit="V"),
          'VGate_i':self.dut["CCPD_VGate"].get_current(unit="mA"),
          'Vcasc_v':self.dut["CCPD_Vcasc"].get_voltage(unit="V"),
          'Vcasc_i':self.dut["CCPD_Vcasc"].get_current(unit="mA"),
          'BL_v':self.dut["CCPD_BL"].get_voltage(unit="V"),
          'BL_i':self.dut["CCPD_BL"].get_current(unit="mA"),
          'Th_v':self.dut["CCPD_Th"].get_voltage(unit="V"),
          'Th_i':self.dut["CCPD_Th"].get_current(unit="mA"),
          'PCB_Th_v':self.dut["PCB_Th"].get_voltage(unit="V"),
          'PCB_Th_i':self.dut["PCB_Th"].get_current(unit="mA"),
          #'RX_output_en':self.dut["rx"].get_output_en()[0],
          'RX_data':str(self.dut["rx"].get_data())}
    def measure(self,exp):
        if exp>0.0001:
            self.dut['CCPD_TDC'].set_en(True)
        self.start_pulser()
        if exp>0.0001:
            time.sleep(exp)
            self.dut['CCPD_TDC'].set_en(False)
            data=self.get_data_now()
        else:
            data=self.get_data()
        return data
    def run_fei4scan(self,scan="Ext"):
        if scan=="ext":
            self.rmg.run_run(HvcmosScan)
        elif scan=="tune":
            
            self.rmg.run_run(ThresholdBaselineTuning)
        elif scan=="self":
            self.rmg.run_run(HvcmosSelfScan)
        else:
            print "scan have to be ext, self, or tune"
            return
         
        filename=self.get_fei4file()
        self.l.append("FEI4Scan:%f"%filename)
        if scan=="ext" or scan=="self":
            print np.asarray(load_fei4data("%s_interpreted.h5"%filename,dataname="HistOcc"),int)
        
    def tune_with_fei4(self,th=0.9,VNDAC=10,VNCout=4):
        print "WARNING WARNING WARNING WARNING WARNING WARNING WARNING"
        print "WRNING   This tuning algorithm is not robust    WARNING"
        print "WARNING WARNING WARNING WARNING WARNING WARNING WARNING"
        for v in [0,1,2]:
            if v==0:
                   v1=VNCout
                   v2=0
                   v3=0
            elif v==1:
                   v1=0
                   v2=VNCout
                   v3=0
            elif v==2:
                   v1=0
                   v2=0
                   v3=VNCout
            t=-1
            pix=[]
            noisylist=[]
            for ii in range(150):
             #### set tdacs
                if t==-1 and v==0:
                    tdacs=np.copy(self._tdacs)*0+7
                flg=0
                for p in pix:
                    if tdacs[p[0],p[1]]==t and t!=0:
                        print "*******setting",p,
                        print "tdac=",tdacs[p[0],p[1]]-1
                        tdacs[p[0],p[1]]=tdacs[p[0],p[1]]-1
                        flg=1
                    elif tdacs[p[0],p[1]]==0 :
                        print "!!!!!!!add noisy pix!!!!!!",p
                        noisylist.append(p)
                if flg==0:
                    t=t+1
                    if t==16:
                       break
                    for i in range(12,48):
                        for j in range(24):
                            if t==0 and i%3==v:
                              tdacs[j,i]=0
                            elif tdacs[j,i]==t-1 and i%3==v:
                              tdacs[j,i]=t
             #measure
                self.set(th=th,VNDAC=VNDAC,VNCOut1=v1,tdac=tdacs,VNCOut2=v2,VNCOut3=v3)
                self.rmg.run_run(HvcmosSelfScan,run_conf={"scan_timeout":1})
                f=self.get_fei4file()
             ### calc for next t
                try:
                     data=self.load_fei4data(f)
                except:
                     data=np.zeros([12,24])
                print np.asarray(data,int)
                pix_fei4=np.argwhere(data>10)
                pix=[]
                for p in pix_fei4:
                    print "result pix=",p,data[p[0],p[1]],
                    flg=0
                    if flg==0:
                        p=self.fei42hvcmos(p,v)
                        print p,"tdac=",int(self._tdacs[p[0],p[1]])
                        pix.append(p)
    #######################
    #### useful functions
    def save_tdac(self):
        tdacs=np.zeros([24*60,3])
        for i in range(60):
            for j in range(24):
                tdacs[i*24+j]=[j,i,self.tdacs[j,i]]
        np.savetxt("tdacs.txt",tdacs)
    def get_fei4file(self,datadir=r"D:\workspace\pybar\branches\development\pybar\module_test"):
        fno=open(os.path.join(datadir,"run.cfg")).readlines()[-1].split()[0]
        for f in os.listdir(datadir):
            ftmp=f.split("_")
            if "interpreted.h5"==ftmp[-1] and fno==ftmp[0]:
                return os.path.join(datadir,f)
        return None
    def fei42hvcmos(self,pix,vncout):
        debug=0
        row_base=(11-pix[0])*2
        col=(15-pix[1]/2)*3+vncout
        if debug==1:
            print pix[0]%2,pix[1]%2,vncout,row_base
        if (pix[0]%2==1 and pix[1]%2==0) and (vncout==1):
            if debug==1:
                print "odd,even"
            row=row_base+1
        elif (pix[0]%2==1 and pix[1]%2==1) and (vncout==0 or vncout==2):
            if debug==1:
                print "odd,odd 1"
            row=row_base+1
        elif (pix[0]%2==0 and pix[1]%2==1) and (vncout==1):
            row=row_base+1
        elif (pix[0]%2==0 and pix[1]%2==0) and (vncout==0 or vncout==2):
            if debug==1:
                print "even,even 1"
            row=row_base+1
        else:
            if debug==1:
                print "odd,even 0"
                print "even,odd 0"
            row=row_base
        return [row,col]
    def hvcmos2fei4(self,pix):
        pass       
    def load_fei4data(self,filename,dataname="HistOcc"):
        import tables 
        f=tables.openFile(filename)
        if dataname=="HistOcc#3":
            data=np.transpose(f.root.HistOcc[206:230,0:12,0])
            #direct_pix=f.root.HistOcc[197,11,0]
        elif dataname=="HistOcc" or dataname=="HistOcc#2":
            data=np.transpose(f.root.HistOcc[184:208,0:12,0])
        f.close()
        return data
