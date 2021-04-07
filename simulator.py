import pandas as pd
import os
import sys
import io
import ALU
import memory
import IAG
from register import RegisterFile
from decode import identify
from helperFunctions import *
from input import ReadFile
 
class Processor:

    def __init__(self, currFolderPath):
        self._PMI = memory.PMI()
        self._ALU = ALU.ALU()
        self._IAG = IAG.IAG()
        self._fileReader = ReadFile()
        self._registerFile = RegisterFile()
        self._currFolderPath = currFolderPath
        self.df_control = pd.read_csv(os.path.join(self._currFolderPath, 'repository', "controls.csv"))
        self.df_control = self.df_control.dropna(axis=0, how='any')
        self.df_main = pd.read_csv(os.path.join(self._currFolderPath, 'repository', "instructions.csv"))

        self._outputLogFile = open(os.path.join(self._currFolderPath, 'generated', "outputLog.txt"), "w")
        self.initialiseTempRegisters()
        self.initialiseControls()
        
        sys.stdout = self._outputLogFile
        self._currOperationId = 0
        self.cycle = 0

    def initialiseTempRegisters(self):
        self._IR = '0'*8
        self._RA = '0'*8
        self._RB = '0'*8
        self._rd = 0
        self._RZ = '0'*8
        self._RM = '0'*8
        self._RY = '0'*8
        self._imm = '0'*8

    def initialiseControls(self):
        self._ALU_select = list(self.df_control['ALU_select'].astype(int))
        self._muxB = list(self.df_control['muxB'].astype(int))
        self._muxA = list(self.df_control['muxA'].astype(int))
        self._muxY = list(self.df_control['muxY'].astype(int))
        self._memoryEnable = list(self.df_control['ME'].astype(int))
        self.INC_select = list(self.df_control['muxINC'].astype(int))
        self.PC_select = list(self.df_control['muxPC'].astype(int))
        self.S_select = list(self.df_control['muxS'].astype(int))
        self._writeEnable = list(self.df_control['WE'].astype(int))
        self.SizeEnable = list(self.df_control['SE'].astype(int))

    def muxMA(self, MA_select):
        if(MA_select == 0):
            return self._RZ
        else:
            return self._IAG.getPC()
        

    def setIR(self, enable):
        if enable == 1:
            self._IR = self._PMI.getMDR()
            
    def getIR(self):
        return self._IR

    def muxA(self, A_select):
        if(A_select == 0):
            return self._RA
        else:
            return self._IAG.getPC()

    def muxB(self, B_select):
        if(B_select == 0):
            return self._RB
        else:
            return self._imm

    def muxY(self, Y_select):
        if(Y_select == 0):
            return self._RZ
        elif(Y_select == 1):
            return self._PMI.getMDR()
        else:
            return self._IAG.getPC_Temp()

    def load_mc(self, currFileName):
        filepath = os.path.join(self._currFolderPath,'test', currFileName)
        self._fileReader.read_mc(filepath, self._PMI)

    def fetch(self):
        print("Fetch stage:")
        print("The value of PC is :", self._IAG.getPC())
        outputmuxMA = self.muxMA(1)  # MAR gets value of PC
        self._IAG.updatePC_temp()  # PC_Temp gets PC+4
        self._PMI.setMAR(outputmuxMA)
        # MDR gets value stored at address in MAR
        self._PMI.accessMemory(1,2)
        self.setIR(1)  # IR gets value of MDR
        print("The instruction in IR is :", self._IR)

    def decode(self):
        print("Decode stage:")
        info_code = identify(self._IR, self.df_main)
        print("code :", info_code)
        self._currOperationId = info_code['id']

        registernumber = int(info_code['rs1'], 2)
        self._RA = self._registerFile.get_register(registernumber)
        print("RA is :", self._RA)

        registernumber = int(info_code['rs2'], 2)
        self._RB = self._registerFile.get_register(registernumber)
        self._RM = self._RB
        print("RB is :", self._RB)

        rd = int(info_code['rd'], 2)
        self._rd = rd
        print("rd is :", self._rd)

        immediate = extendImmediate(info_code['immediate'])
        self._imm = binToHex(immediate)
        print("imm is :", self._imm)


    def execute(self):
        print("Execute stage:")
        currALU_select = self._ALU_select[self._currOperationId]
        currMuxB = self._muxB[self._currOperationId]
        currMuxA = self._muxA[self._currOperationId]
        currINCSelect = self.INC_select[self._currOperationId]
        currSSelect = self.S_select[self._currOperationId]

        operand1 = self.muxA(currMuxA)
        operand2 = self.muxB(currMuxB)
        print("operand1 is", operand1, "operand2 is:", operand2)
        self._RZ = self._ALU.operate(operand1, operand2, currALU_select)
        print("RZ is :", self._RZ)
        self._IAG.muxPC(self.PC_select[self._currOperationId], self._RA)
        self._IAG.updatePC(1)
        self._IAG.muxINC(currINCSelect, currSSelect, self._imm, self._RZ)
        self._IAG.adder()
        self._IAG.muxPC(0, self._RA)
        self._IAG.updatePC(1)

    def memoryAccess(self):
        print("Memory Access stage:")
        currMemoryEnable = self._memoryEnable[self._currOperationId]
        currSizeEnable = self.SizeEnable[self._currOperationId]
        outputmuxMA = self.muxMA(0)
        self._PMI.setMAR(outputmuxMA)
        self._PMI.setMDR(self._RM)
        self._PMI.accessMemory(currMemoryEnable, currSizeEnable)
        self._RY = self.muxY(self._muxY[self._currOperationId])

    def registerUpdate(self):
        print("Register Update Stage:")
        currWriteEnable = self._writeEnable[self._currOperationId]
        self._registerFile.set_register(self._rd, self._RY, currWriteEnable)
        print("RD: RY:", self._rd, self._RY)
        self.cycle += 1
        print("cycle is :", self.cycle)

    def printData(self):
        filename = 'output.txt'
        filename = os.path.join(self._currFolderPath, "generated", 'memory.txt')
        memorySnapshot = self._PMI.getMemory()
        self._fileReader.printMemory(memorySnapshot, filename)
        self._outputLogFile.close()

    def printRegisters(self):
        registers = self._registerFile.get_registerFile()
        filename = os.path.join(self._currFolderPath, "generated", 'registers.txt')
        self._fileReader.printRegisters(registers, filename)
        
        
    def getRegisters(self):
        return self._registerFile.get_registerFile()
        
    def getData(self):
        return self._PMI.getMemory()

    def reset(self):
        self._registerFile.initialise_registers()
        self._PMI.clearMemory()
        self._IAG.initialiseIAG()
        self.initialiseTempRegisters()
        self.initialiseControls()
        self.cycle = 0