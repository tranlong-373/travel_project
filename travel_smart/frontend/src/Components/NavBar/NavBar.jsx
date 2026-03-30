import React from 'react'
import styles from './NavBar.module.css'
import vector from '../../assets/Vector.png'
import down from '../../assets/chevron-down.png'
const NavBar = () => {
    return (
        <div className='fixed left-0 right-0 top-0 w-full bg-white'>
            <div className='flex justify-between items-center py-4 px-6 md:px-20 lg:px-32'>
                <div className='text-2xl font-bold text-blue-500'>CheckIn</div>
                <div className='flex justify-between font-semibold'>
                    <ul className='items-center flex gap-7'>
                        <li>Home</li>
                        <li>About us</li>
                        <li>Contact</li>
                    </ul>
                    <div className='flex items-center ml-20'>
                        <div className='flex mr-4 w-[20px] mr-10'>
                            <img src={vector} alt="" />
                            <img className='ml-2' src={down} alt="" />
                        </div>
                        <button className='rounded-lg px-4 py-2 bg-blue-500'>
                            <p className='text-white'>Log In</p>
                        </button>
                    </div>
                </div>
            </div>
        </div>
    )
}

export default NavBar