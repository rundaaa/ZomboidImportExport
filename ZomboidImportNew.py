# Author: Jab (or 40BlocksUnder) | Joshua Edwards
# Link for more info: http://theindiestone.com/forums/index.php/topic/12864-blender
# Imports models from Zomboid format.

bl_info = {
    "name": "ZomboidImport",
    "description": "Imports models from Zomboid format.",
    "author": "Jab",
    "version": (1, 0),
    "blender": (2, 79, 0),
    "location": "",
    "warning": "", # used for warning icon and text in addons panel
    "wiki_url": "http://theindiestone.com/forums/index.php/topic/12864-blender"
                "Scripts/My_Script",
    "tracker_url": "https://developer.blender.org/maniphest/task/edit/form/2/",
    "support": "COMMUNITY",
    "category": "Import-Export",
}


import traceback
import io,math,bmesh,bpy

from bpy import context
from bpy.types import Operator
from bpy.props import FloatVectorProperty
from bpy_extras.object_utils import AddObjectHelper, object_data_add
from mathutils import Vector, Euler, Quaternion, Matrix
from bpy_extras.io_utils import ImportHelper
from bpy.props import StringProperty, BoolProperty, EnumProperty
from bpy.types import Operator
from math import pi

class ZomboidImport(Operator, ImportHelper):
    """This appears in the tooltip of the operator and in the generated docs"""
    
    # important since its how bpy.ops.import_test.some_data is constructed
    bl_idname    = "zomboid.import_model"
    bl_label     = "Import a Zomboid Model"
    filename_ext = ".txt"
    filter_glob  = StringProperty(
            default="*.txt",
            options={'HIDDEN'},
            )
    
    load_model = BoolProperty(
        name="Load Model",
        description="Whether or not to import the model mesh.",
        default=True,
        )
        
    optimize_model = BoolProperty(
        name="Optimize Model",
        description="Removing double vertex groups, merging them, and converting Triangular polygons to quads.",
        default=False,
        )
    
    load_armature = BoolProperty(
        name="Load Armature",
        description="Whether or not to import the armature, if present.",
        default=True,
        )
    
    load_weights = BoolProperty(
        name="Load Bone Weights",
        description="Load Bone weights if PZ armature is detected. (RECOMENDED!)",
        default=True,
        )
    
    load_animations = BoolProperty(
        name="Load Animations (WIP!)",
        description="Whether or not to import animations. (Not done yet!)",
        default=True,
        )
    
    lock_model_on_armature_detection = BoolProperty(
        name="Lock Model Transforms If Armature Present",
        description="Whether or not to lock the model, if an armature is present.",
        default=True,
        )
        
    should_optimize_armature = BoolProperty(
        name="Optimize Armature (Biped Models)",
        description="Optimizes the imported Armature for animation purposes.",
        default=False,
        )
    

    # Get the current scene
    #scene = context.scene

#####################################################################################
###                                                                               ###
###   File I/O                                                                    ###
###                                                                               ###
#####################################################################################      

    def read_header(self,file):
        z               = self.z_mesh
        z.version       = read_float(file)
        z.name          = read_line(file)
        z.element_count = read_int(file)
        read_int(file)
        
        for x in range(0, z.element_count):
            value = read_line(file)
            type  = read_line(file)
            z.stride_type.append(type)
            
            if type == "TextureCoordArray":
                z.has_texture = True
            elif type == "BlendWeightArray":
                z.has_weights = True


    def read_vertex_buffer(self,file):
        z = self.z_mesh
        z.vertex_count = read_int(file)
        for x in range(0,int(z.vertex_count)):
            for element in range(0,z.element_count):
                e = z.stride_type[element]
                if e == "VertexArray":
                    line = read_line(file)
                    vs = line.split(', ')
                    z.vertices.append(Vector((float(vs[0]), float(vs[1]), float(vs[2]))))
                elif e == "TextureCoordArray":
                    line = read_line(file)
                    vs = line.split(', ')
                    z.uvs.append(Vector((float(vs[0]),float(1) - float(vs[1]))))
                elif e == "BlendWeightArray":
                    weights = read_line(file)
                    split   = weights.split(", ")
                    array   = []
                    for s in split:
                        array.append(float(s))
                    z.weight_values.append(array)
                elif e == "BlendIndexArray":
                    indexes = read_line(file)
                    split   = indexes.split(", ")
                    array   = []
                    for s in split:
                        array.append(int(s))
                    z.weight_indexes.append(array)
                else:
                    line = read_line(file)
    
                    
    def read_faces(self,file):
        z = self.z_mesh
        z.face_count = read_int(file)
        for x in range(0, z.face_count):     
            face        = read_line(file)    
            vertices    = face.split(", ")
            vertices[0] = int(vertices[0])
            vertices[1] = int(vertices[1])
            vertices[2] = int(vertices[2])
            z.faces.append([vertices[0], vertices[1], vertices[2]])
            if z.has_texture:
                z.face_uvs.append([z.uvs[vertices[0]],z.uvs[vertices[1]],z.uvs[vertices[2]]])


    def read_skeleton(self,file):                                       
        z = self.z_mesh
        skeleton = z.skeleton
        skeleton.bone_count = read_int(file)
        for index in range(0, skeleton.bone_count):                 
            bone_index                       = read_int (file)     
            bone_parent_index                = read_int (file)     
            bone_name                        = read_line(file)     
            skeleton.bone_index [bone_name ] = bone_index          
            skeleton.bone_name  [bone_index] = bone_name           
            skeleton.bone_parent[bone_index] = bone_parent_index   
        for index in range(0,skeleton.bone_count):                 
            bone_index                       = read_int(file)      
            bone_matrix                      = read_matrix(file)   
            skeleton.bind_matrix[bone_index] = bone_matrix         
        for index in range(0,skeleton.bone_count):                 
            read_int(file)                                              
            read_matrix(file)                                           
        for index in range(0,skeleton.bone_count):                 
            bone_index = read_int(file)                                 
            skeleton.offset_matrix[bone_index] = read_matrix(file) 
       

    def read_animations(self,file):    
        z = self.z_mesh
        skeleton = z.skeleton
        z.animation_count = read_int(file)
        for animation_index in range(0,z.animation_count):
            animation_name        = read_line(file)
            animation_time        = read_float(file)
            animation_frame_count = read_int(file)
            if self.DEBUG:
                print("Reading Animation: " + animation_name + "...")
            
            key_frames            = []
            frame                 = Frame()
            current_index         = -1
            last_index            = -1
            first                 = False
            
            animation = Animation(animation_name,animation_time,animation_frame_count)
            z.animations.append(animation)
            
            for keyframe_index in range(0, animation_frame_count):     
                current_index     = read_int(file)
                if current_index < last_index:
                    for index, kf in enumerate(key_frames):
                        frame.bones.append(kf.bone_index)
                        frame.bone_names.append(kf.bone_name)
                        frame.times.append(kf.time)
                        frame.bone_locs[kf.bone_name] = kf.loc
                        frame.bone_rots[kf.bone_name] = kf.rot
                    
                    frame.key_frames = key_frames
                    animation.frames.append(frame)
                    key_frames = []
                    frame = Frame()
                    
                last_index = current_index
                
                bone_name  = read_line(file)
                frame_time = read_float(file)
                loc        = read_vector(file)
                rot        = read_quaternion(file) 
                mat        = rot.to_matrix().to_4x4() * Matrix.Translation(loc).to_4x4()

                key_frame     = KeyFrame(current_index,bone_name,frame_time,mat)
                key_frame.loc = loc
                key_frame.rot = rot
                key_frames.append(key_frame)
                
            
            for kf in key_frames:
                frame.bones.append(kf.bone_index)
                frame.bone_names.append(kf.bone_name)
                frame.times.append(kf.time)
                frame.bone_locs[kf.bone_name] = kf.loc
                frame.bone_rots[kf.bone_name] = kf.rot

            frame.key_frames = key_frames
            animation.frames.append(frame)

#####################################################################################
###                                                                               ###
###   Blender methods                                                             ###
###                                                                               ###
#####################################################################################

    def create_mesh(self):
        try:
            bpy.ops.object.mode_set(mode='OBJECT')
        except:
            ok = True
        
        try:
            bpy.ops.object.select_all(action='DESELECT')
        except:
            ok = True
        
        z = self.z_mesh
        self.scene = bpy.context.scene
        
        z.mesh = bpy.data.meshes.new(name=z.name)
        z.mesh.from_pydata(z.vertices, z.edges, z.faces)
        z.mesh.update(calc_tessface=True)
        # Safety Duplicate Name Check.
        z.name = z.mesh.name

        object_data_add(context, z.mesh)
        
        bpy.ops.object.select_pattern(pattern=z.name)
        z.object = bpy.context.active_object
        z.mesh = z.object.data
        
        bpy.ops.object.mode_set(mode = 'EDIT')
        # UV Assignments
        bm = bmesh.from_edit_mesh(z.mesh)
        uv_layer = bm.loops.layers.uv.verify()
        bm.faces.layers.tex.verify()
        voffset = 0
        for f in bm.faces:
            index = f.index
            uv_array = z.face_uvs[index]
            vo = 0
            for l in f.loops:
                luv = l[uv_layer]
                luv.uv = uv_array[vo]
                vo += 1
        bmesh.update_edit_mesh(z.mesh)
        
        if z.has_armature:
            bpy.ops.object.mode_set(mode = 'OBJECT')
            if self.lock_model_on_armature_detection:
                z.object.lock_location = z.object.lock_rotation = z.object.lock_scale = [True, True, True]
            
            
            print(z.skeleton.object)
            old_active = bpy.context.active_object     
            self.scene.objects.active = z.skeleton.object 
            z.object.select = True                          
            bpy.ops.object.parent_set(type='ARMATURE')                       
            self.scene.objects.active = old_active                    
            z.object.select = False                         
           
            bpy.ops.object.mode_set(mode = 'OBJECT')

            # Weight Assignments
            for bone in z.skeleton.armature.bones:
                bpy.ops.object.vertex_group_add()
                vertex_group      = z.object.vertex_groups.active    
                vertex_group.name = bone.name
                bone_import_index = int(z.skeleton.object[bone.name])

                offset_vert = 0
                for vertex in z.mesh.vertices:
                    vertex_weight_ids = z.weight_indexes[offset_vert]
                    vertex_weights    = z.weight_values[offset_vert]
                    
                    offset = 0
                    for vert_weight_id in vertex_weight_ids:
                        if vert_weight_id == bone_import_index:
                            verts = []
                            verts.append(vertex.index)
                            vertex_group.add(verts, vertex_weights[offset], 'REPLACE')
                        offset += 1
                    offset_vert += 1
        
        if self.optimize_model:
            bpy.ops.object.mode_set(mode = 'EDIT')
            bpy.ops.mesh.remove_doubles()
            bpy.ops.mesh.tris_convert_to_quads()
            bpy.ops.object.mode_set(mode = 'OBJECT')


    def create_armature(self):
        try:
            bpy.ops.object.mode_set(mode='OBJECT')
            bpy.ops.object.select_all(action='DESELECT')
        except:
            ok = None
        
        z                        = self.z_mesh
        skeleton                 = z.skeleton
        skeleton.name            = z.name + "_armature"
        skeleton.armature        = bpy.data.armatures.new(skeleton.name)
        skeleton.object = bpy.data.objects.new(skeleton.name, skeleton.armature)
        skeleton.name   = skeleton.object.name 
        
        self.scene.objects.link(skeleton.object)
        self.scene.objects.active = skeleton.object
        
        skeleton.object.select     = True
        skeleton.object.show_x_ray = True
        
        bpy.ops.object.mode_set(mode='EDIT')
        
        for bone_index in range(0, skeleton.bone_count):
        
            bone_name = skeleton.bone_name[bone_index]
            bone = skeleton.armature.edit_bones.new(bone_name)
        
            if self.DEBUG:
                print('Creating Bone: ' + bone_name)
        
            parent_matrix = Matrix.Identity(4).inverted()
            if bone_index != 0:
                parent_index = skeleton.bone_parent[bone_index]
                parent = skeleton.bones[parent_index]
                bone.parent = parent
                
            skeleton.bones[bone_index] = skeleton.bones[bone_name] = bone
            bone.head = Vector((0, 0, 0    ))
            
            mat = skeleton.offset_matrix[bone_index].to_blender_matrix().inverted()
            
            if bone_name == 'Bip01':
                print(bone_name + ": ")
                print("Offset Before: ")
                print(skeleton.offset_matrix[bone_index])
                print("Offset After: ")
                print(to_lwjgl_matrix(blender_matrix=mat.copy().inverted()))
                
            skeleton.bind_pose[bone_name] = mat
            bone.matrix = mat
            bone.tail = Vector((bone.head.x, bone.head.y + 0.075, bone.head.z)) 
        
        bpy.ops.object.mode_set(mode='OBJECT')
        
        skeleton.object["ZOMBOID_ARMATURE"] = 1 
        for index in range(0, skeleton.bone_count):
            bpy.ops.wm.properties_add(data_path="object.data")
            skeleton.object[skeleton.bone_name[index]] = index
        
        z.load_armature = True
        
        
    def create_animations(self):
        z = self.z_mesh
        s = z.skeleton
        s.armature.show_axes = True
        
        # Set ourselves into the pose mode of the armature with nothing selected.
        bpy.ops.object.select_all(action='DESELECT')
        bpy.ops.object.select_pattern(pattern=s.name)
        bpy.ops.object.mode_set(mode='POSE')
        bpy.ops.pose.select_all(action='DESELECT')
        
        frame_offset = 0
        
        # Go through each Animation.
        for animation in z.animations:
            if animation.name != "Run":
                continue
            s.object.animation_data_create();
            s.object.animation_data.action = bpy.data.actions.new(animation.name)
            s.object.animation_data.action.use_fake_user = 1
            if self.DEBUG == True:
                print("Rendering Animation: " + animation.name + "...")
            
            frame_offset = 0
            p_bones = [ ]
            
            s.bone_pose  = dict()
            s.world_pose = dict()
            s.skin_pose  = dict()
            
            last_matrix = dict()
            should_mat  = dict()
            for bone_index in range(0, s.bone_count):
                last_matrix[bone_index] = Matrix()
                should_mat[bone_index] = False
            
            for frame in animation.frames:
                bpy.data.scenes[0].frame_current = frame_offset                    
                
                s.armature
                #if self.DEBUG == True:
                    #print('Rendering Frame: ' + str(frame_offset))
                
                # 1) Turn the translation and rotation into a Frame Matrix
                # 2) Create a World Matrix by multiplying the Parent World Matrix with the Frame Matrix
                # 3) Create the Product Matrix by multiplying the World Matrix with the Bone Matrix
                
                
                for bone_index in range(0, s.bone_count):
                    bone_name    = s.bone_name[bone_index]
                    try:
                        l = frame.bone_locs[bone_name].copy()
                        r = frame.bone_rots[bone_name].copy()
                        s.bone_pose[bone_index] = s.bone_pose[bone_name] = create_from_quaternion_position(r,l)
                    except:
                        ok = None
                    
                s.world_pose[0] = mul(s.bone_pose[0], Matrix4f(), None)
                for bone_index in range(1, s.bone_count):
                    parent_index = s.bone_parent[bone_index]                    
                    s.world_pose[bone_index] = mul(s.bone_pose[bone_index].copy(), s.world_pose[parent_index].copy(), None)
    
                                    
                for bone_index in range(0, s.bone_count):
                    bone_name   = s.bone_name[bone_index]
                    parent_index = s.bone_parent[bone_index]
                    s.skin_pose[bone_index] = mul(s.offset_matrix[bone_index].copy(), s.world_pose[bone_index].copy(), None)
                                    
                for bone_index in range(1, s.bone_count):
                    bone_name   = s.bone_name[bone_index]
                    bone        = s.object.pose.bones[bone_name]
                    s.poses[bone_name] = bone
                    if bone_name == 'Root':
                        continue
                    p_bones.append(bone)
                    
                    bone_index = s.bone_index[bone_name]
                    
                    mat = s.skin_pose[bone_index].to_blender_matrix()
                    
                    if mat != last_matrix[bone_index]: 
                        
                        bpy.ops.object.select_pattern(pattern=bone_name) 
                        
                        parent_index = s.bone_parent[bone_index]

                        bone.matrix = mat.copy() * bone.bone.matrix_local.copy()
                            
                        bpy.ops.object.mode_set(mode='OBJECT')
                        bpy.ops.object.mode_set(mode='POSE')
                        
                        bpy.context.scene.update()
                        self.scene.update()
                        try:
                            bpy.ops.anim.keyframe_insert_menu(type='Location')
                        except:
                            ok = None
                        try:
                            bpy.ops.anim.keyframe_insert_menu(type='Rotation')
                        except:
                            ok = None
                        
                        bpy.ops.pose.select_all(action='DESELECT')
                        
                        last_matrix[bone_index] = mat

                self.scene.update()
                bpy.ops.pose.select_all(action='DESELECT')
                frame_offset += 1
        
        
    def execute(self, context):
        
        self.scene = bpy.context.scene
        old_cursor = self.scene.cursor_location
        self.scene.cursor_location = (0.0, 0.0, 0.0)
        z = self.z_mesh
        #scene = bpy.context.scene
        # The offset in the file read
        offset = 0

        with io.open(self.filepath, 'r') as file:
            end_of_file = False
            while file.readable() and end_of_file == False:
                    if offset == 0:
                        self.read_header(file)
                    elif offset == 3:
                        self.read_vertex_buffer(file)
                    elif offset == 5:
                        self.read_faces(file)
                    elif offset == 6:
                        try:
                            self.read_skeleton(file)
                            z.has_armature = True
                            z.load_armature = True
                        except:
                            end_of_file       = True
                            traceback.print_exc()
                    elif offset == 9:
                        try:
                            self.read_animations(file)
                            z.has_animations  = True
                        except: 
                            end_of_file = True
                            traceback.print_exc()
                    
                    offset+=1
                    if offset > 10 or end_of_file:
                        break
                    
            # Close the file.
            file.close()
        
        if z.has_armature and self.load_armature:
            self.create_armature()
        if self.load_animations and z.has_animations:
            self.create_animations()
            
        # Check for meshes with Blend data and no armature.
        if z.has_armature == False and z.has_weights == True:
            print('pass')
            valid_arm     = False
            armature_name = ''
            
            for object in bpy.data.objects:
                try:
                    test = object["ZOMBOID_ARMATURE"]
                    if test != -1:
                        print('hasArmature')
                        z.skeleton.object = object
                        z.skeleton.armature = object.data
                        z.skeleton.name  = object.name
                        z.has_armature = True
                        print('success')
                        valid_arm = True
                        break
                except:
                    ok = True
            
            if valid_arm:
                for bone in z.skeleton.object.data.bones:
                    bone_name = bone.name
                    index = z.skeleton.bone_index[bone_name] = z.skeleton.object[bone_name]
                    z.skeleton.bone_name[index] = bone_name
                
        if self.load_model:
            self.create_mesh()
        
        bpy.context.scene.cursor_location = old_cursor
        
        return {'FINISHED'}
        

    def __init__(self):
        self.z_mesh                             = ZMesh()
        self.DEBUG                              = True


class ZMesh:
    
    def __init__(self):
        
        self.name             = ''
        self.skeleton         = Skeleton()
        self.animations       = [ ]
        self.animation_count  = [ ]
        
        #############################
        # FILE I/O              # # #
        #############################
        self.element_count  = 0
        self.elements       = [ ]
        self.stride_type    = [ ]
        self.weight_values  = [ ]
        self.weight_indexes = [ ]
        #############################
        # BLENDER               # # #
        #############################
        self.object         = None
        self.mesh           = None
        self.faces          = [ ]
        self.face_uvs       = [ ]
        self.edges          = [ ]
        self.vertices       = [ ]
        self.uvs            = [ ]
        #############################
        # FLAGS                 # # #
        #############################
        self.has_texture    = False
        self.has_armature   = False
        self.load_armature  = False
        self.has_animations = False
        self.has_weights    = False

class Skeleton:
    
    def __init__(self):
        self.name          = ''
        #############################
        # FILE I/O              # # #
        #############################
        self.bone_count    = 0      # NUMBER OF BONES.
        self.bone_index    = dict() # KEY: BONE_NAME
        self.bind_pose     = dict() # KEY: BONE_ID | BONE_NAME
        self.world_pose    = dict()
        self.bind_matrix   = dict() # KEY: BONE_ID
        self.offset_matrix = dict() # KEY: BONE_ID
        self.bone_name     = dict() # KEY: BONE_ID
        self.bone_parent   = dict() # KEY: BONE_ID
        #############################
        # BLENDER               # # #
        #############################
        self.animations    = [ ]    #
        self.object        = None   #
        self.armature      = None   #
        self.bones         = dict() #
        self.poses         = dict() #
        #############################

class Animation:
    def __init__(self,name,time,frame_count):
        self.name        = name
        self.time        = time
        self.frame_count = frame_count
        self.key_frames  = [ ]
        self.frames      = [ ]

class Frame:
    def __init__(self):
        self.bone_matrices_index = dict()
        self.bone_transforms     = dict()
        self.world_transforms    = dict()
        self.skin_transforms     = dict()
        self.bone_matrices       = dict()
        self.key_frames          = [ ]
        self.bones               = [ ]
        self.bone_names          = [ ]
        self.times               = [ ]    
        self.bone_mats           = [ ]
        self.bone_locs           = dict()
        self.bone_rots           = dict()
           
class KeyFrame:
    def __init__(self,bone_index,bone_name,frame_time,mat):
        self.bone_index = bone_index
        self.bone_name  = bone_name
        self.time       = frame_time
        self.matrix     = mat
        self.loc        = Vector((0,0,0))
        self.rot        = Quaternion()


def menu_func_import(self, context):
    self.layout.operator(ZomboidImport.bl_idname, text="Zomboid Mesh (.txt)")
    
def register():
    bpy.utils.register_class(ZomboidImport)
    bpy.types.INFO_MT_file_import.append(menu_func_import)

def unregister():
    bpy.utils.unregister_class(ZomboidImport)
    bpy.types.INFO_MT_file_import.remove(menu_func_import)

if __name__ == "__main__":
    register()
    bpy.ops.zomboid.import_model('INVOKE_DEFAULT')
    
#####################################################################################
###                                                                               ###
###   File I/O methods                                                            ###
###                                                                               ###
#####################################################################################                   
          
def read_line(file):
    string = '#'
    while string.startswith("#"):
        string = str(file.readline().strip())
    return string
  
                  
def read_int(file):
    return int(read_line(file))


def read_float(file):
    return float(read_line(file))


def read_vector(file):
    line = read_line(file)
    split = line.split(", ")
    var = Vector((float(split[0]), float(split[1]), float(split[2])))
    return var


def read_quaternion(file):
    line = read_line(file)
    split = line.split(", ")
    
    x = float(split[0])
    y = float(split[1])
    z = float(split[2])
    w = float(split[3])
    return Quaternion((w,x,y,z))

def normalise(q):
    len = length(q)
    if len != 0.0:
        l = 1.0 / len
        scale(q,l)

def scale(q,l):
    q.x = q.x * l
    q.y = q.y * l
    q.z = q.z * l
    q.w = q.w * l

def length(q):
    return math.sqrt(length_squared(q))

def length_squared(q):
    return (q.x * q.x + q.y * q.y + q.z * q.z + q.w * q.w)

def create_from_quaternion(q):
    
    if length(q) > 0.0:
        normalise(q)
    
    xx = q.x * q.x
    xy = q.x * q.y
    xz = q.x * q.z
    wx = q.x * q.w
    yy = q.y * q.y
    yz = q.y * q.z
    wy = q.y * q.w
    zz = q.z * q.z
    wz = q.z * q.w
 
    mat = Matrix4f()
    
    mat.m00 = 1.0 - 2.0 * (yy + zz)
    mat.m10 =       2.0 * (xy - wz)
    mat.m20 =       2.0 * (xz + wy)
    mat.m30 =       0.0
    mat.m01 =       2.0 * (xy + wz)
    mat.m11 = 1.0 - 2.0 * (xx + zz)
    mat.m21 =       2.0 * (yz - wx) * 1.0
    mat.m31 =       0.0
    mat.m02 =       2.0 * (xz - wy)
    mat.m12 =       2.0 * (yz + wx)
    mat.m22 = 1.0 - 2.0 * (xx + yy)
    mat.m32 =       0.0
    mat.m03 =       0.0
    mat.m13 =       0.0
    mat.m23 =       0.0
    mat.m33 =       1.0
    mat.m30 =       0.0
    mat.m31 =       0.0
    mat.m32 =       0.0
   
#    mat = Matrix(
#          ([m00, m01, m02, m03],
#           [m10, m11, m12, m13],
#           [m20, m21, m22, m23],
#           [m30, m31, m32, m33])).copy().transposed()
    
    return transpose(mat,None)    

def create_from_quaternion_position(rotation, position):
    mat = create_from_quaternion(rotation)
    mat2 = Matrix4f()
    mat2 = translate(position, mat2, None)
    mat2 = transpose(mat2, None)
    mat3 = Matrix4f()
    mul(mat, mat2, mat3)
    return mat3

def read_matrix(file):
    s1 = read_line(file).split(", ")
    s2 = read_line(file).split(", ")
    s3 = read_line(file).split(", ")
    s4 = read_line(file).split(", ")
    
    mat = Matrix4f()
    
    mat.m00 = float(s1[0])
    mat.m01 = float(s1[1])
    mat.m02 = float(s1[2])
    mat.m03 = float(s1[3])
    mat.m10 = float(s2[0])
    mat.m11 = float(s2[1])
    mat.m12 = float(s2[2])
    mat.m13 = float(s2[3])
    mat.m20 = float(s3[0])
    mat.m21 = float(s3[1])
    mat.m22 = float(s3[2])
    mat.m23 = float(s3[3])
    mat.m30 = float(s4[0])
    mat.m31 = float(s4[1])
    mat.m32 = float(s4[2])
    mat.m33 = float(s4[3])

    return mat    

#    m = Matrix(
#        ([m00, m01, m02, m03],
#         [m04, m05, m06, m07],
#         [m08, m09, m10, m11],
#         [m12, m13, m14, m15]))
#
#    m = Matrix(
#        ([m00, m10, m20, m30],
#         [m01, m11, m21, m31],
#         [m02, m12, m22, m32],
#         [m03, m13, m23, m33]))
#         
#    return m.transposed()


def quat_equals(q1,q2):
    return q1.w == q2.w and q1.x == q2.x and q1.y == q2.y and q1.z == q2.z


quat_transform_y_positive = Euler((pi/2, 0, 0),"XYZ").to_quaternion()

m4 = Matrix(
        ([1, 0, 0, 0],
         [0, 0, -1, 0],
         [0, 1, 0, 0],
         [0, 0, 0, 1]))

m3 = Matrix(
        ([1, 0, 0],
         [0, 0, -1],
         [0, 1, 0]))

matrix_3_transform_y_positive = Matrix((( 1, 0, 0 )   ,( 0, 0, 1 )   ,( 0,-1, 0 )                  ))
matrix_4_transform_y_positive = Matrix((( 1, 0, 0, 0 ),( 0, 0, 1, 0 ),( 0,-1, 0, 0 ),( 0, 0, 0, 1 )))
matrix_3_transform_z_positive = Matrix((( 1, 0, 0 )   ,( 0, 0,-1 )   ,( 0, 1, 0 )                  ))
matrix_4_transform_z_positive = Matrix((( 1, 0, 0, 0 ),( 0, 0,-1, 0 ),( 0, 1, 0, 0 ),( 0, 0, 0, 1 )))

class Matrix4f():
    
    def __init__(self):
        self.m00 = 1.0
        self.m01 = 0.0
        self.m02 = 0.0
        self.m03 = 0.0
        self.m10 = 0.0
        self.m11 = 1.0
        self.m12 = 0.0
        self.m13 = 0.0
        self.m20 = 0.0
        self.m21 = 0.0
        self.m22 = 1.0
        self.m23 = 0.0
        self.m30 = 0.0
        self.m31 = 0.0
        self.m32 = 0.0
        self.m33 = 1.0
        
    def __str__(self):
        return 'Matrix4f' + '\n[' + efloat(self.m00) + ', ' + efloat(self.m01) + ', ' + efloat(self.m02) + ', ' + efloat(self.m03) + '],\n[' + efloat(self.m10) + ', ' + efloat(self.m11) + ', ' + efloat(self.m12) + ', ' + efloat(self.m13) + '],\n[' + efloat(self.m20) + ', ' + efloat(self.m21) + ', ' + efloat(self.m22) + ', ' + efloat(self.m23) + '],\n[' + efloat(self.m30) + ', ' + efloat(self.m31) + ', ' + efloat(self.m32) + ', ' + efloat(self.m33) + ']'
        
    def set_identity(self):
        self.m00 = 1.0
        self.m01 = 0.0
        self.m02 = 0.0
        self.m03 = 0.0
        self.m10 = 0.0
        self.m11 = 1.0
        self.m12 = 0.0
        self.m13 = 0.0
        self.m20 = 0.0
        self.m21 = 0.0
        self.m22 = 1.0
        self.m23 = 0.0
        self.m30 = 0.0
        self.m31 = 0.0
        self.m32 = 0.0
        self.m33 = 1.0
        
    def copy(self):
        nm = Matrix4f()
        nm.m00 = self.m00
        nm.m01 = self.m01
        nm.m02 = self.m02
        nm.m03 = self.m03
        nm.m10 = self.m10
        nm.m11 = self.m11
        nm.m12 = self.m12
        nm.m13 = self.m13
        nm.m20 = self.m20
        nm.m21 = self.m21
        nm.m22 = self.m22
        nm.m23 = self.m23
        nm.m30 = self.m30
        nm.m31 = self.m31
        nm.m32 = self.m32
        nm.m33 = self.m33
        return nm
    
    def to_blender_matrix(self):
        m = Matrix(
         ([self.m00, self.m10, self.m20, self.m30],
          [self.m01, self.m11, self.m21, self.m31],
          [self.m02, self.m12, self.m22, self.m32],
          [self.m03, self.m13, self.m23, self.m33]))
        return m.transposed()

def to_lwjgl_matrix(blender_matrix):
    m = Matrix4f()
    b = blender_matrix.copy().transposed()
    m.m00 = b[0][0]
    m.m01 = b[1][0]
    m.m02 = b[2][0]
    m.m03 = b[3][0]
    m.m10 = b[0][1]
    m.m11 = b[1][1]
    m.m12 = b[2][1]
    m.m13 = b[3][1]
    m.m20 = b[0][2]
    m.m21 = b[1][2]
    m.m22 = b[2][2]
    m.m23 = b[3][2]
    m.m30 = b[0][3]
    m.m31 = b[1][3]
    m.m32 = b[2][3]
    m.m33 = b[3][3]
    return m

def translate(vec, src, dest):
    if dest == None:
        dest = Matrix4f()
    
    dest.m30 += src.m00 * vec.x + src.m10 * vec.y + src.m20 * vec.z
    dest.m31 += src.m01 * vec.x + src.m11 * vec.y + src.m21 * vec.z
    dest.m32 += src.m02 * vec.x + src.m12 * vec.y + src.m22 * vec.z
    dest.m33 += src.m03 * vec.x + src.m13 * vec.y + src.m23 * vec.z
    
    return dest

def mul(left,right,dest):
    if dest == None:
        dest = Matrix4f()
    
    m00 = left.m00 * right.m00 + left.m10 * right.m01 + left.m20 * right.m02 + left.m30 * right.m03
    m01 = left.m01 * right.m00 + left.m11 * right.m01 + left.m21 * right.m02 + left.m31 * right.m03
    m02 = left.m02 * right.m00 + left.m12 * right.m01 + left.m22 * right.m02 + left.m32 * right.m03
    m03 = left.m03 * right.m00 + left.m13 * right.m01 + left.m23 * right.m02 + left.m33 * right.m03
    m10 = left.m00 * right.m10 + left.m10 * right.m11 + left.m20 * right.m12 + left.m30 * right.m13
    m11 = left.m01 * right.m10 + left.m11 * right.m11 + left.m21 * right.m12 + left.m31 * right.m13
    m12 = left.m02 * right.m10 + left.m12 * right.m11 + left.m22 * right.m12 + left.m32 * right.m13
    m13 = left.m03 * right.m10 + left.m13 * right.m11 + left.m23 * right.m12 + left.m33 * right.m13
    m20 = left.m00 * right.m20 + left.m10 * right.m21 + left.m20 * right.m22 + left.m30 * right.m23
    m21 = left.m01 * right.m20 + left.m11 * right.m21 + left.m21 * right.m22 + left.m31 * right.m23
    m22 = left.m02 * right.m20 + left.m12 * right.m21 + left.m22 * right.m22 + left.m32 * right.m23
    m23 = left.m03 * right.m20 + left.m13 * right.m21 + left.m23 * right.m22 + left.m33 * right.m23
    m30 = left.m00 * right.m30 + left.m10 * right.m31 + left.m20 * right.m32 + left.m30 * right.m33
    m31 = left.m01 * right.m30 + left.m11 * right.m31 + left.m21 * right.m32 + left.m31 * right.m33
    m32 = left.m02 * right.m30 + left.m12 * right.m31 + left.m22 * right.m32 + left.m32 * right.m33
    m33 = left.m03 * right.m30 + left.m13 * right.m31 + left.m23 * right.m32 + left.m33 * right.m33
    dest.m00 = m00
    dest.m01 = m01
    dest.m02 = m02
    dest.m03 = m03
    dest.m10 = m10
    dest.m11 = m11
    dest.m12 = m12
    dest.m13 = m13
    dest.m20 = m20
    dest.m21 = m21
    dest.m22 = m22
    dest.m23 = m23
    dest.m30 = m30
    dest.m31 = m31
    dest.m32 = m32
    dest.m33 = m33
    
    return dest

def transpose(src, dest):
    if dest == None:
        dest = Matrix4f()
    
    m00 = src.m00
    m01 = src.m10
    m02 = src.m20
    m03 = src.m30
    m10 = src.m01
    m11 = src.m11
    m12 = src.m21
    m13 = src.m31
    m20 = src.m02
    m21 = src.m12
    m22 = src.m22
    m23 = src.m32
    m30 = src.m03
    m31 = src.m13
    m32 = src.m23
    m33 = src.m33
    dest.m00 = m00
    dest.m01 = m01
    dest.m02 = m02
    dest.m03 = m03
    dest.m10 = m10
    dest.m11 = m11
    dest.m12 = m12
    dest.m13 = m13
    dest.m20 = m20
    dest.m21 = m21
    dest.m22 = m22
    dest.m23 = m23
    dest.m30 = m30
    dest.m31 = m31
    dest.m32 = m32
    dest.m33 = m33
    
    return dest

scale_matrix_4 = Matrix(
                ([-1,0,0,0],
                 [ 0,1,0,0],
                 [ 0,0,1,0],
                 [ 0,0,0,1]))
  
def get_keyframes(obj_list):
    keyframes = []
    for obj in obj_list:
        anim = obj.animation_data
        if anim is not None and anim.action is not None:
            for fcu in anim.action.fcurves:
                for keyframe in fcu.keyframe_points:
                    x, y = keyframe.co
                    if x not in keyframes:
                        keyframes.append((math.ceil(x)))
    return keyframes

def efloat(float):
    return "%0.8f" % float