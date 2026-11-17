"""Execute the standalone preview JavaScript and check its motion geometry."""
import json, os, unittest
from pathlib import Path
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication
from PySide6.QtQml import QJSEngine

class PreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.js=QJSEngine()
        stub="""
        var ops=[],c={};
        ['setTransform','clearRect','fillRect','beginPath','moveTo','lineTo','quadraticCurveTo','bezierCurveTo','closePath','fill','stroke','save','restore','translate','rotate','scale','ellipse','fillText'].forEach(k=>c[k]=(...a)=>ops.push([k,...a]));
        c.createLinearGradient=()=>({addColorStop(){}});
        function el(){return {append(){},addEventListener(){},setAttribute(){},querySelector(){return el();},getContext(){return c;}};}
        var document={querySelector(){return el();},querySelectorAll(){return [];},createElement(){return el();},addEventListener(){}};
        function requestAnimationFrame(){};
        """
        self.js.evaluate(stub)
        code=Path(__file__).with_name('model-lab.html').read_text(encoding='utf-8').split('<script>')[1].split('</script>')[0]
        result=self.js.evaluate(code+"\nvar previewTest={frame(st,t){ops=[];state=st;draw(views[0],t);return JSON.stringify(ops);},leg(t){ops=[];leg(c,models[0],0,0,t);return JSON.stringify(ops);},head(st,t){ops=[];neckHead(c,models[0],t,st);return JSON.stringify(ops);}};")
        self.assertFalse(result.isError(),result.toString())
    def call(self,code):
        result=self.js.evaluate(code)
        self.assertFalse(result.isError(),result.toString())
        return json.loads(result.toString())
    def test_all_actions_execute_across_cycle_boundaries(self):
        for state in ('walk','eat','sleep','fly','poop'):
            for t in (0,.3,1,2.5,5,9.5,12,17.9):
                self.assertGreater(len(self.call('previewTest.frame('+json.dumps(state)+','+str(t)+')')),100)
    def test_planted_foot_moves_backward_with_flat_contact(self):
        a=self.call('previewTest.leg(Math.PI+.2)')
        b=self.call('previewTest.leg(2*Math.PI-.2)')
        a=next(op for op in a if op[0]=='lineTo')
        b=next(op for op in b if op[0]=='lineTo')
        self.assertGreater(a[1],b[1])
        self.assertEqual(a[2],b[2])
    def test_chewing_head_reaches_lower_than_fire_pose(self):
        def pivot(st):
            return next(op for op in self.call('previewTest.head('+json.dumps(st)+',0)') if op[0]=='translate')
        fire,chew=pivot('fire'),pivot('chew')
        self.assertGreater(chew[2],fire[2]+40)
        self.assertGreater(chew[1],fire[1])
        self.assertLess(abs(chew[2]+29),4)

if __name__=='__main__':unittest.main()
